"""Real loader/dispatcher/PTB group Add, false injection permission, no network.

Transport-only capture. This is not live Telegram acceptance.
"""
import asyncio
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, PropertyMock

from native_telegram import prepare
from native_telegram_lifecycle import ForumRunner
from test_telegram import Capture
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager, PluginContext
from hermes_state import SessionDB
from gateway.config import Platform, PlatformConfig
from gateway.session import SessionSource, build_session_key
from plugins.platforms.telegram.adapter import TelegramAdapter
from telegram import Update
from telegram.ext import Application
from tools.registry import registry


async def main():
    with tempfile.TemporaryDirectory(prefix='shelf-native-add-', dir=os.environ.get('TMPDIR')) as directory:
        home = Path(directory)/'home'
        prepare(home)
        config = home/'config.yaml'
        config.write_text(config.read_text().replace('allow_gateway_injection: true', 'allow_gateway_injection: false'))
        bound = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        app = db = None
        try:
            with ExitStack() as guards:
                injection = guards.enter_context(patch.object(PluginContext, 'inject_message', side_effect=AssertionError('No injection allowed')))
                llm = guards.enter_context(patch.object(PluginContext, 'llm', new_callable=PropertyMock,
                                                       side_effect=AssertionError('No LLM allowed')))
                await asyncio.to_thread(manager.discover_and_load)
                loaded = [p for p in manager.list_plugins() if p['name']=='delivery-shelf']
                assert len(loaded)==1 and not loaded[0]['error'], loaded
                capture = Capture()
                app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(capture).updater(None).build()
                await app.initialize()
                # Exercise native handler wiring, not just a direct factory call.
                adapter = TelegramAdapter(PlatformConfig())
                with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                    adapter._wire_plugin_handlers(app)
                controller = manager.get_platform_handler_factories('telegram')[0][0].__self__
                handler = manager._plugin_commands['shelf']['handler']
                search = registry.get_entry('delivery_shelf_search', scope=manager.scope_key).handler
                runner = ForumRunner()
                runner.profile = controller.profile
                source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100', chat_type='group',
                    user_id='17', thread_id='9', message_id='22', profile='default')
                now = datetime.now(timezone.utc)
                session = SimpleNamespace(session_id='group-session', session_key=build_session_key(source),
                                          created_at=now, updated_at=now)
                db = SessionDB(home/'state.db')
                db.create_session(session.session_id, source='telegram', user_id='18')
                def deliver(*names):
                    return db.append_message(session.session_id, 'assistant', '\n'.join(
                        'MEDIA:'+str(home/'workspaces'/name) for name in names))
                async def command(args):
                    return await runner._hm_run_plugin_handler(handler, None, source, session_entry=session, args=args)
                def entries():
                    return json.loads(search({}))['data']['items']
                def buttons():
                    return [button for row in capture.calls[-1][1]['reply_markup']['inline_keyboard'] for button in row]
                async def click(data, message, user=17, thread=9):
                    await app.process_update(Update.de_json({'update_id':1,'callback_query':{
                        'id':'fictional','from':{'id':user,'is_bot':False,'first_name':'Fixture'},
                        'chat_instance':'fictional','data':data,
                        'message':{'message_id':message,'date':1,'message_thread_id':thread,
                                   'chat':{'id':-100,'type':'supergroup'},'text':'Shelf'}}}, app.bot))
                deliver('first.md')
                assert await command('add') is None
                first = entries()[0]
                assert first['title']=='first.md' and first['session_id']==session.session_id
                assert capture.calls[-1][1]['message_thread_id']==9
                assert 'Saved to Delivery Shelf' in capture.calls[-1][1]['text']
                assert await command('add Different #Ignored --description "Keep existing"') is None
                assert entries()==[first]
                assert 'Already saved' in capture.calls[-1][1]['text']
                # A newer delivery set wins; preview does not save anything.
                deliver('first.md','second.md')
                assert await command('') is None
                add = buttons()[0]['callback_data']
                message = capture.serial
                await click(add, message)
                choices = buttons()
                assert [b['text'] for b in choices]==['first.md','second.md','Cancel']
                assert entries()==[first]
                for who, topic in ((18,9),(17,10)):
                    await click(choices[1]['callback_data'], message, who, topic)
                    assert capture.calls[-1][1]['show_alert']
                    assert entries()==[first]
                await click(choices[1]['callback_data'], message)
                saved = entries()
                assert len(saved)==2 and saved[0]['file']['path']=='second.md'
                await click(choices[1]['callback_data'], message)
                assert capture.calls[-1][1]['show_alert'] and entries()==saved
                # Reviewer reproduction through the actual loader and PTB transport:
                # old choice -> save -> View -> Add newer set -> failed publication.
                for name in ('old.md', 'new.md', 'third.md'):
                    (home/'workspaces'/name).write_text('Fictional publication regression')
                for outcome in ('rejected', 'cancelled'):
                    deliver('old.md', 'new.md')
                    assert await command('add') is None
                    old_choice, message = buttons()[1]['callback_data'], capture.serial
                    await click(old_choice, message)
                    await click(buttons()[0]['callback_data'], message)  # View saved file
                    add = buttons()[0]['callback_data']
                    deliver('old.md', 'third.md')
                    before = entries()
                    start = len(capture.calls)
                    if outcome == 'rejected':
                        capture.fail.add('editMessageText')
                        await click(add, message)
                        rejected = [d for v,d in capture.calls[start:] if v == 'editMessageText']
                        assert len(rejected) == 2  # replacement AND error confirmation
                        unpublished = rejected[0]['reply_markup']['inline_keyboard'][1][0]['callback_data']
                        capture.fail.clear()
                    else:
                        entered = asyncio.Event()
                        real_request = capture.do_request
                        pending = []
                        async def delayed(url, method, request_data=None, **kwargs):
                            response = await real_request(url, method, request_data=request_data, **kwargs)
                            data = request_data.parameters if request_data else {}
                            if url.endswith('/editMessageText') and data.get('text') == 'Shelf · Choose a file to save':
                                pending.append(data['reply_markup']['inline_keyboard'][1][0]['callback_data'])
                                entered.set()
                                await asyncio.Event().wait()  # cancelled before acknowledgement
                            return response
                        with patch.object(capture, 'do_request', delayed):
                            task = asyncio.create_task(click(add, message))
                            try:
                                await asyncio.wait_for(entered.wait(), 2)
                                await click(pending[0], message)
                                assert capture.calls[-1][1]['show_alert'] and entries() == before
                            finally:
                                task.cancel()
                                result = await asyncio.gather(task, return_exceptions=True)
                                assert isinstance(result[0], asyncio.CancelledError)
                        unpublished = pending[0]
                    for stale in (old_choice, unpublished):
                        await click(stale, message)
                        assert capture.calls[-1][1]['show_alert'] and entries() == before
                    assert await command('add') is None
                    retry_buttons, retry_message = buttons(), capture.serial
                    assert retry_buttons[1]['callback_data'] not in (old_choice, unpublished)
                    await click(retry_buttons[-1]['callback_data'], retry_message)
                    assert 'Cancelled' in capture.calls[-1][1]['text'] and entries() == before
                assert await command('add') is None
                await click(buttons()[1]['callback_data'], capture.serial)
                saved = entries()
                assert len(saved) == len(before) + 1 and saved[0]['file']['path'] == 'third.md'
                # Lifecycle hook fencing still owns session reset.
                assert await command('add') is None
                stale = buttons()[0]['callback_data']
                message = capture.serial
                manager.invoke_hook('on_session_reset', old_session_id=session.session_id, session_id='fresh')
                await click(stale, message)
                assert capture.calls[-1][1]['show_alert'] and entries()==saved
                injection.assert_not_called()
                llm.assert_not_called()
                print('PASS native PluginManager + TelegramAdapter wiring + GatewayRunner dispatcher + real PTB Application')
                print('PASS shared-topic owner differs from original session author; false injection permission; zero injection/LLM access')
                print('PASS command direct save/readback; exact duplicate unchanged; panel Add -> exact chooser -> authenticated direct save')
                print('PASS rejected chooser AND error edits, cancelled edit, unpublished/stale replay refusal, clean retry and exact save')
                print('PASS foreign owner/topic, replay and reset refusal; capture transport only, no live Telegram send')
        finally:
            if db is not None:
                db.close()
            manager.unload()
            if app is not None:
                await app.shutdown()
            reset_hermes_home_override(bound)


if __name__=='__main__': asyncio.run(main())
