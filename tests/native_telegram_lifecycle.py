"""Real host wiring/reload + forum dispatch, no network or production state."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from native_telegram import prepare
from test_telegram import Capture
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager
from gateway.config import Platform, PlatformConfig
from gateway.session import SessionSource, build_session_key
from gateway.run import GatewayRunner
from plugins.platforms.telegram.adapter import TelegramAdapter


class ForumRunner(GatewayRunner):
    # Skip service startup, but inherit actual dispatcher and task-bound source
    # binding. Only the executor is local; no scheduler, model or live transport.
    def __init__(self):
        from gateway.config import GatewayConfig
        self.config = GatewayConfig()
        self.adapters = {}
        self.profile = 'default'
    def _session_key_for_source(self, source): return build_session_key(source)
    async def _run_in_executor_with_context(self, func, *args):
        return await asyncio.to_thread(func, *args)


async def main():
    with tempfile.TemporaryDirectory(prefix='shelf-native-lifecycle-', dir=os.environ.get('TMPDIR')) as directory:
        home = Path(directory) / 'home'
        prepare(home)
        token = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        apps = []
        try:
            adapter = TelegramAdapter(PlatformConfig())
            async def application():
                capture = Capture()
                app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(capture).updater(None).build()
                await app.initialize()
                apps.append(app)
                return app, capture
            app, capture = await application()
            runner = ForumRunner()
            source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100', chat_type='group', user_id='17', thread_id='9', profile='default')
            now = datetime.now(timezone.utc)
            entry = SimpleNamespace(session_key=build_session_key(source), session_id='forum-session', created_at=now, updated_at=now)
            def controller():
                return manager.get_platform_handler_factories('telegram')[0][0].__self__
            async def panel():
                runner.profile = controller().profile
                return await runner._hm_run_plugin_handler(manager._plugin_commands['shelf']['handler'], None, source, session_entry=entry, args='')
            with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                # Actual connect wiring before plugins exist, then late registration.
                adapter._wire_plugin_handlers(app)
                core_calls = []
                async def core(update, context): core_calls.append(update)
                core_handler = CallbackQueryHandler(core)
                app.add_handler(core_handler)
                adapter._core_handler_ids = {id(core_handler)}
                await asyncio.to_thread(manager.discover_and_load)
                adapter.rewire_plugin_handlers()
                first = controller()
                assert await panel() is None
                assert capture.calls[-1][1]['chat_id'] == -100
                assert capture.calls[-1][1]['message_thread_id'] == 9
                assert 'inline_keyboard' in capture.calls[-1][1]['reply_markup']
                print('PASS native late-load wiring and actual forum-topic dispatcher')
                # The same lifecycle used by the supported reload-plugins control verb.
                await asyncio.to_thread(manager.discover_and_load, force=True)
                adapter.rewire_plugin_handlers()
                assert not first.alive and controller() is not first
                result = await panel()
                # Installed host dedupes (plugin, factory.__qualname__), not the
                # new registration. It retires the old controller but never binds
                # the replacement. Characterize the host gap, not a plugin fix.
                replacement = controller()
                assert replacement.application is None
                assert replacement.permitted(replacement.identity(source, entry.session_id, entry.session_key, 'telegram'))
                assert isinstance(result, str) and 'Delivery Shelf' in result
                print('CONFIRMED host reload gap: authorized replacement factory skipped; no PTB Application')
                # Only the fixture initializes adapter transport internals; plugin
                # code still receives PTB exclusively through the public factory.
                adapter._bot = app.bot
                model = await adapter.send_model_picker('-100', [
                    {'slug': 'openai', 'name': 'Fixture provider', 'models': ['fixture-model'], 'is_current': True}
                ], 'fixture-model', 'openai', entry.session_key, lambda *args: None,
                    metadata={'thread_id': '9'})
                assert model.success, model.error
                assert capture.calls[-1][1]['message_thread_id'] == 9
                assert 'inline_keyboard' in capture.calls[-1][1]['reply_markup']
                print('PASS native /model picker still sends inline markup in same topic during Shelf reload gap')
                app, capture = await application()
                adapter._wire_plugin_handlers(app)  # actual native-client rebuild path
                assert replacement.application is app
                assert await panel() is None
                nonce, state = next(iter(replacement.panels.items()))
                assert capture.calls[-1][1]['message_thread_id'] == 9
                async def click(user=17, thread=9):
                    await app.process_update(Update.de_json({'update_id': 1, 'callback_query': {
                        'id': 'fixture', 'from': {'id': user, 'is_bot': False, 'first_name': 'Fixture'},
                        'chat_instance': 'fixture', 'data': f'shelf:{nonce}:0',
                        'message': {'message_id': int(state.message), 'date': 1, 'message_thread_id': thread,
                                    'chat': {'id': -100, 'type': 'supergroup'}, 'text': 'Shelf'}}}, app.bot))
                await click(user=18)
                assert capture.calls[-1][0] == 'answerCallbackQuery' and capture.calls[-1][1]['show_alert']
                await click(thread=10)
                assert capture.calls[-1][0] == 'answerCallbackQuery' and capture.calls[-1][1]['show_alert']
                await click()
                assert capture.calls[-1][0] == 'editMessageText'
                assert not core_calls
                print('PASS native-client rebuild restores topic panel; owner/topic callback guards preserved')
        finally:
            manager.unload()
            for app in apps: await app.shutdown()
            reset_hermes_home_override(token)


if __name__ == '__main__': asyncio.run(main())
