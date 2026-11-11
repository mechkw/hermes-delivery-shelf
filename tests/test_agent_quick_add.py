"""Native loader regression tests; only disposable profiles and captured transport."""
import asyncio
from contextlib import ExitStack
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from native_telegram import prepare, ROOT
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager
from hermes_cli.plugin_command_dispatch import invoke_plugin_command
from hermes_state import SessionDB


class QuickAddNativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shelf-agent-native-', dir=os.environ.get('TMPDIR'))
        self.home = Path(self.temp.name)/'home'
        prepare(self.home)
        # Include newly shipped modules, not merely the historical fixture list.
        import shutil
        for source in ROOT.glob('agent_*.py'):
            shutil.copy2(source, self.home/'plugins/delivery-shelf'/source.name)
        self.bound = set_hermes_home_override(self.home)
        self.guards = ExitStack()
        self.manager = PluginManager(str(self.home))
        await asyncio.to_thread(self.manager.discover_and_load)
        infos = [p for p in self.manager.list_plugins() if p['name']=='delivery-shelf']
        self.assertEqual(len(infos), 1)
        self.assertFalse(infos[0]['error'], infos)
        self.controller = self.manager.get_platform_handler_factories('telegram')[0][0].__self__
        self.api = self.controller.api
        self.store = self.api.Store(self.home)
        self.db = SessionDB(self.home/'state.db')
        self.db.create_session('native-current', source='desktop')

    async def asyncTearDown(self):
        self.db.close()
        self.manager.unload()
        self.guards.close()
        reset_hermes_home_override(self.bound)
        self.temp.cleanup()

    def deliver(self, *names):
        return self.db.append_message('native-current', 'assistant', '\n'.join(
            'MEDIA:'+str(self.home/'workspaces'/name) for name in names))

    async def command(self, text='add Exact #Keep --description "Literal."', **kwargs):
        context = dict(platform='desktop', session_id='native-current', session_key='native-route') | kwargs
        result = invoke_plugin_command(self.manager._plugin_commands['shelf']['handler'], text, **context)
        return await result if inspect.isawaitable(result) else result

    async def test_quick_add_saves_latest_completed_set_with_generated_details(self):
        from types import SimpleNamespace
        from unittest.mock import patch, PropertyMock
        from hermes_cli.plugins import PluginContext
        self.db.append_message('native-current', 'user', 'Prepare the fictional field notes.')
        self.deliver('first.md')
        latest = self.deliver('first.md', 'second.md')
        calls = []
        async def complete(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(parsed={'title':'Field notes', 'description':'Fictional selected notes.', 'tags':['Notes']})
        with patch.object(PluginContext, 'llm', new_callable=PropertyMock,
                return_value=SimpleNamespace(acomplete_structured=complete)):
            reply = await self.command('add')
        self.assertEqual(reply, 'Saved to Delivery Shelf: Field notes (+1 files)')
        item = self.store.search()['items'][0]
        self.assertEqual(item['files'], [{'root':'workspaces','path':'first.md'}, {'root':'workspaces','path':'second.md'}])
        self.assertEqual(item['tags'], ['Notes'])
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(item['versions'][0]['files']), 2)
        self.assertNotIn('\n', reply)
        self.assertEqual(self.controller.panels, {})

    async def test_native_telegram_quick_add_has_no_chooser(self):
        from native_telegram_lifecycle import ForumRunner
        from gateway.config import Platform
        from gateway.session import SessionSource
        from datetime import datetime, timezone
        from types import SimpleNamespace
        self.deliver('first.md', 'second.md')
        self.controller.application = object()  # Command transport is host-owned, not used for sends.
        source = SessionSource(platform=Platform.TELEGRAM, chat_id='17', chat_type='dm',
            user_id='17', profile=self.controller.profile)
        runner = ForumRunner()
        runner.profile = self.controller.profile
        now = datetime.now(timezone.utc)
        session = SimpleNamespace(session_id='native-current', session_key='native-route', created_at=now, updated_at=now)
        result = await runner._hm_run_plugin_handler(self.manager._plugin_commands['shelf']['handler'],
            None, source, session_entry=session, args='add Exact #Keep --description "Literal."')
        self.assertEqual(result, 'Saved to Delivery Shelf: Exact')
        self.assertEqual(len(self.store.search()['items'][0]['files']), 2)
        self.assertEqual(self.controller.panels, {})

    async def test_unknown_startup_reset_does_not_permanently_reject_new_explicit_add(self):
        self.deliver('first.md')
        self.manager.invoke_hook('on_session_reset')
        reply = await self.command()
        self.assertEqual(reply, 'Saved to Delivery Shelf: Exact')
        saved = self.store.search()['items']
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['session_id'], 'native-current')
        # An identified retired generation is still denied, not revived by reset.
        self.manager.invoke_hook('on_session_reset', old_session_id='native-current', session_id='new')
        reply = await self.command()
        self.assertIn('Conversation or profile changed', reply)
        self.assertEqual(self.store.search()['total'], 1)
