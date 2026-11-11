"""Reported Telegram Shelf contracts through real host dispatch and PTB capture.

Every home/catalog is task-owned. No live Telegram transport or provider call.
"""
import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent))
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


class ReportedTelegramRegressions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shelf-reported-', dir=os.environ.get('TMPDIR'))
        self.home = Path(self.tmp.name) / 'home'
        prepare(self.home)
        self.bound = set_hermes_home_override(self.home)
        self.guards = ExitStack()
        self.model_calls = []
        async def complete(**kwargs):
            self.model_calls.append(kwargs)
            return SimpleNamespace(parsed={'title':'Native saved report', 'description':'Selected content.', 'tags':['saved']})
        self.guards.enter_context(patch.object(PluginContext, 'llm', new_callable=PropertyMock,
            return_value=SimpleNamespace(acomplete_structured=complete)))
        self.injection = self.guards.enter_context(patch.object(PluginContext, 'inject_message',
            side_effect=AssertionError('Native shelf must not inject an agent turn')))
        self.manager = PluginManager(str(self.home))
        await asyncio.to_thread(self.manager.discover_and_load)
        self.adapter = TelegramAdapter(PlatformConfig())
        self.apps = []
        await self.rebuild_native()
        self.runner = ForumRunner()
        self.runner.profile = self.controller.profile
        self.source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100', chat_type='group',
            user_id='17', thread_id='9', message_id='22', profile='default')
        now = datetime.now(timezone.utc)
        self.session = SimpleNamespace(session_id='reported-session', session_key=build_session_key(self.source),
            created_at=now, updated_at=now)
        self.db = SessionDB(self.home/'state.db')
        self.db.create_session(self.session.session_id, source='telegram', user_id='18')
        row = self.db.append_message(self.session.session_id, 'assistant', 'Prepare the selected native report.')
        # Avoid importing the interactive user-message classifier in this fixture.
        import sqlite3
        with sqlite3.connect(self.home/'state.db') as conn:
            conn.execute("UPDATE messages SET role='user' WHERE id=?", (row,))
        self.api = self.controller.api
        self.store = self.api.Store(self.home)

    @property
    def controller(self):
        return self.manager.get_platform_handler_factories('telegram')[0][0].__self__

    async def rebuild_native(self):
        self.capture = Capture()
        self.app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(self.capture).updater(None).build()
        await self.app.initialize()
        self.apps.append(self.app)
        with patch('hermes_cli.plugins.get_plugin_manager', return_value=self.manager):
            self.adapter._wire_plugin_handlers(self.app)

    async def asyncTearDown(self):
        self.db.close()
        self.manager.unload()
        for app in self.apps:
            await app.shutdown()
        self.guards.close()
        reset_hermes_home_override(self.bound)
        self.tmp.cleanup()

    def deliver(self, *names):
        for name in names:
            (self.home/'workspaces'/name).write_bytes(('Exact managed bytes: '+name).encode())
        return self.db.append_message(self.session.session_id, 'assistant', '\n'.join(
            'MEDIA:'+str(self.home/'workspaces'/name) for name in names))

    async def command(self, args=''):
        handler = self.manager._plugin_commands['shelf']['handler']
        return await self.runner._hm_run_plugin_handler(handler, None, self.source,
            session_entry=self.session, args=args)

    def buttons(self):
        return [b for row in self.capture.calls[-1][1]['reply_markup']['inline_keyboard'] for b in row]

    async def manual_add(self):
        self.assertIsNone(await self.command('menu'))
        await self.click('Add')

    async def quick_save(self, args, expected):
        before = list(self.capture.calls)
        result = await self.command(args)
        self.assertEqual(result, expected)
        self.assertEqual(result.splitlines(), [expected])
        self.assertEqual(self.capture.calls, before, 'Quick save must not send an inline chooser')
        return self.store.search()['items'][0]

    async def click(self, label, *, user=17, thread=9):
        data = next(b['callback_data'] for b in self.buttons() if b['text']==label)
        panel = next(reversed(self.controller.panels.values()))
        await self.app.process_update(Update.de_json({'update_id':1, 'callback_query':{
            'id':'reported', 'from':{'id':user,'is_bot':False,'first_name':'Fixture'},
            'chat_instance':'reported', 'data':data,
            'message':{'message_id':int(panel.message),'date':1,'message_thread_id':thread,
                'chat':{'id':-100,'type':'supergroup'},'text':'Shelf'}}}, self.app.bot))

    async def test_r2_retrieves_only_second_most_recently_saved_not_two_files(self):
        self.deliver('older.md', 'newest.md')
        older = self.store.create(self.api.EntryInput(title='Older', file={'root':'workspaces','path':'older.md'}))
        self.store.create(self.api.EntryInput(title='Newest', file={'root':'workspaces','path':'newest.md'}))
        # A later metadata correction must not make the older registration newest.
        self.store.update(older['id'], self.api.EntryUpdate.model_validate({
            **{k:older[k] for k in ('title','description','tags','kind','project','file','files','session_id')},
            'title':'Corrected older', 'revision':older['revision']}))
        (self.home/'workspaces/older.md').unlink()
        (self.home/'workspaces/newest.md').unlink()
        result = await self.command('r2')
        self.assertEqual(result, 'Shelf · File sent.')
        self.assertEqual([u[2]['document'][1] for u in self.capture.uploads], [b'Exact managed bytes: older.md'])
        self.assertEqual(self.capture.uploads[0][1]['message_thread_id'], 9)
        self.assertEqual(self.model_calls, [])
        self.injection.assert_not_called()

    async def test_add_r1_saves_newest_one_without_chooser_or_literal_r1_title(self):
        self.deliver('first.md')
        self.deliver('second.md', 'last.md')
        saved = await self.quick_save('add r1', 'Saved to Delivery Shelf: Native saved report')
        items = self.store.search()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(self.store.get(saved['id']), saved)
        self.assertEqual(items[0]['files'], [{'root':'workspaces','path':'last.md'}])
        self.assertEqual(items[0]['title'], 'Native saved report')
        self.assertEqual(len(self.model_calls), 1)
        self.assertIn('last.md', str(self.model_calls[0]['input']))
        self.assertEqual(self.controller.panels, {})
        (self.home/'workspaces/last.md').unlink()
        self.assertEqual(await self.command('r1'), 'Shelf · File sent.')
        self.assertEqual(self.capture.uploads[0][2]['document'][1], b'Exact managed bytes: last.md')
        self.injection.assert_not_called()

    async def test_add_r2_spans_recent_answers_and_pins_each_generation_origin(self):
        older_row = self.deliver('older.md')
        newer_row = self.deliver('newer.md')
        saved = await self.quick_save('add r2', 'Saved to Delivery Shelf: Native saved report (+1 files)')
        items = self.store.search()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(self.store.get(saved['id']), saved)
        self.assertEqual([f['path'] for f in items[0]['files']], ['newer.md', 'older.md'])
        self.assertEqual(len(items[0]['versions'][0]['files']), 2)
        self.assertEqual(len(self.model_calls), 2)
        self.assertIn('newer.md', str(self.model_calls[0]['input']))
        self.assertIn('older.md', str(self.model_calls[1]['input']))
        # Metadata is generated against each real source, not a synthetic mixed row.
        module = sys.modules[self.controller.__class__.__module__.rsplit('.',1)[0]+'.recent_artifacts']
        delivery = module.recent(self.home, self.controller.profile, self.session.session_id, count=2)
        refs = module.candidates(self.api, self.home, delivery)
        self.assertEqual([module.generation_request(self.api, delivery, ref, self.session.session_id).source.message_id
            for ref in refs], [newer_row, older_row])
        self.injection.assert_not_called()

    async def test_add_count_invalid_or_short_never_saves_partial_or_treats_selector_as_title(self):
        self.deliver('one.md')
        for args in ('add r0', 'add r01', 'add r9', 'add r2'):
            result = await self.command(args)
            self.assertIsInstance(result, str)
            self.assertIn('Nothing saved', result or '')
            self.assertEqual(self.store.search()['total'], 0)
        self.assertEqual(self.model_calls, [])
        self.assertEqual(self.controller.panels, {})

    async def test_bare_add_quick_saves_exact_recent_set_without_chooser(self):
        self.deliver('first.md', 'second.md')
        saved = await self.quick_save('add', 'Saved to Delivery Shelf: Native saved report (+1 files)')
        self.assertEqual(self.store.search()['total'], 1)
        self.assertEqual(self.store.get(saved['id']), saved)
        self.assertEqual(saved['files'], [
            {'root':'workspaces', 'path':'first.md'}, {'root':'workspaces', 'path':'second.md'}])
        self.assertEqual(saved['session_id'], self.session.session_id)
        self.assertEqual(len(saved['versions'][0]['files']), 2)
        for name in ('first.md', 'second.md'):
            (self.home/'workspaces'/name).unlink()
        for attachment, name in zip(saved['versions'][0]['files'], ('first.md', 'second.md')):
            self.assertEqual(self.api.read_entry_file(self.store, saved,
                file_id=attachment['id'])[1], ('Exact managed bytes: '+name).encode())
        self.assertEqual(await self.command('r1'), 'Shelf · File sent.')
        self.assertEqual(self.capture.uploads[0][2]['document'][1], b'Exact managed bytes: first.md')
        self.injection.assert_not_called()

    async def test_manual_add_keeps_owner_topic_replay_and_revocation_gates(self):
        self.deliver('first.md', 'second.md')
        await self.manual_add()
        labels = [b['text'] for b in self.buttons()]
        self.assertIn('first.md', labels)
        self.assertIn('second.md', labels)
        selected = next(b['callback_data'] for b in self.buttons() if b['text']=='second.md')
        panel = next(reversed(self.controller.panels.values()))
        message = int(panel.message)
        async def replay(user=17, thread=9):
            await self.app.process_update(Update.de_json({'update_id':1, 'callback_query':{
                'id':'guards', 'from':{'id':user,'is_bot':False,'first_name':'Fixture'},
                'chat_instance':'guards', 'data':selected,
                'message':{'message_id':message,'date':1,'message_thread_id':thread,
                    'chat':{'id':-100,'type':'supergroup'},'text':'Shelf'}}}, self.app.bot))
        for user, thread in ((18,9),(17,10)):
            await replay(user, thread)
            self.assertTrue(self.capture.calls[-1][1]['show_alert'])
            self.assertEqual(self.store.search()['total'], 0)
        await replay()
        self.assertEqual(self.store.search()['items'][0]['file']['path'], 'second.md')
        await replay()
        self.assertTrue(self.capture.calls[-1][1]['show_alert'])
        self.assertEqual(self.store.search()['total'], 1)
        policy = self.home/'plugin-data/delivery-shelf/telegram-owners.json'
        policy.write_text('[]')
        with patch.object(self.api, 'Store', side_effect=AssertionError('No unauthorized catalog query')):
            self.assertIn('not authorized', await self.command('r1'))
            self.assertIn('owner policy required', await self.command('add r1'))
        self.assertEqual(self.capture.uploads, [])

    async def test_new_button_actions_do_not_reuse_prior_count_selector(self):
        self.deliver('first.md', 'second.md')
        await self.quick_save('add r1', 'Saved to Delivery Shelf: Native saved report')
        self.assertIsNone(await self.command('search Native saved report'))
        await self.click('Native saved report')
        self.deliver('third.md', 'fourth.md')
        await self.click('Add')
        self.assertIn('third.md', [b['text'] for b in self.buttons()])
        self.assertIn('fourth.md', [b['text'] for b in self.buttons()])
        self.assertEqual(self.store.search()['total'], 1)
        # Open the count-based save through the menu for an explicit version request.
        saved = await self.quick_save('add r1', 'Saved to Delivery Shelf: Native saved report')
        self.assertIsNone(await self.command('search Native saved report'))
        await self.click('Native saved report')
        self.deliver('fifth.md', 'sixth.md')
        await self.click('Add version')
        self.assertIn('fifth.md', [b['text'] for b in self.buttons()])
        self.assertIn('sixth.md', [b['text'] for b in self.buttons()])
        await self.click('fifth.md')
        await self.click('Confirm new version')
        updated = self.store.get(saved['id'])
        self.assertEqual(len(updated['versions']), 2)
        self.assertEqual(updated['files'], [{'root':'workspaces','path':'fifth.md'}])

    async def test_public_reload_gap_names_host_prerequisite_and_native_rebuild_restores_all_paths(self):
        self.deliver('first.md', 'second.md')
        old = self.controller
        self.assertIsNone(await self.command(''))
        self.assertTrue(self.buttons())
        await asyncio.to_thread(self.manager.discover_and_load, force=True)
        with patch('hermes_cli.plugins.get_plugin_manager', return_value=self.manager):
            self.adapter.rewire_plugin_handlers()
        self.assertFalse(old.alive)
        self.assertIsNot(self.controller, old)
        self.assertIsNone(self.controller.application)
        for args in ('', 'add', 'add r1', 'r1'):
            result = await self.command(args)
            self.assertIn('native Telegram', result, (args, result))
            self.assertIn('gateway', result, (args, result))
        self.assertEqual(self.store.search()['total'], 0)
        await self.rebuild_native()
        self.assertIs(self.controller.application, self.app)
        await self.manual_add()
        self.assertIn('first.md', [b['text'] for b in self.buttons()])
        self.assertIn('second.md', [b['text'] for b in self.buttons()])
        self.assertEqual(self.store.search()['total'], 0)
        await self.click('second.md')
        saved = self.store.search()['items'][0]
        self.assertEqual(saved['file']['path'], 'second.md')
        (self.home/'workspaces/second.md').unlink()
        await self.click('View saved file')
        await self.click('Send file')
        self.assertEqual(self.capture.uploads[0][2]['document'][1], b'Exact managed bytes: second.md')
        self.assertIsNone(await self.command(''))
        self.assertTrue(self.buttons())
        self.assertEqual(await self.command('dl 1'), 'Shelf · File sent.')
        self.assertEqual(await self.command('r1'), 'Shelf · File sent.')
        self.assertEqual([u[2]['document'][1] for u in self.capture.uploads],
            [b'Exact managed bytes: second.md'] * 3)
        self.injection.assert_not_called()


class IsolatedNativeRefusalTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_isolated_plugin_host_keeps_native_handlers_unsupported(self):
        with tempfile.TemporaryDirectory(prefix='shelf-reported-isolated-', dir=os.environ.get('TMPDIR')) as directory:
            home = Path(directory)/'home'
            prepare(home, 'host')
            bound = set_hermes_home_override(home)
            manager = PluginManager(str(home))
            try:
                await asyncio.to_thread(manager.discover_and_load)
                info = [p for p in manager.list_plugins() if p['name']=='delivery-shelf']
                self.assertEqual(len(info), 1)
                self.assertFalse(info[0]['error'], info)
                self.assertEqual(manager.get_platform_handler_factories('telegram'), [])
                from hermes_cli.plugin_command_dispatch import invoke_plugin_command
                handler = manager._plugin_commands['shelf']['handler']
                for args in ('r1', 'dl 1'):
                    result = await asyncio.to_thread(invoke_plugin_command, handler, args, platform='telegram')
                    self.assertIn('native Telegram', result)
                    self.assertIn('isolation', result)
                    self.assertIn('Nothing saved or sent', result)
                self.assertIn('isolation: host', (home/'config.yaml').read_text())
            finally:
                manager.unload()
                reset_hermes_home_override(bound)
