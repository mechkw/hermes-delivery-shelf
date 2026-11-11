"""Native PTB capture acceptance for model-backed Add and managed attachments.

Offline only: a structured-model capture replaces the public ctx.llm service;
PTB's BaseRequest capture replaces Telegram, never the controller or Store.
"""
from contextlib import closing
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import test_recent_add as recent_transport
plugin = recent_transport.plugin


class ManagedTelegramTests(recent_transport.RecentAddTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.model_calls = []
        self.disposals = []
        async def complete(**kwargs):
            self.model_calls.append(kwargs)
            values = {
                'title': 'Meadow survey', 'description': 'Three swallows recorded in the meadow.',
                'tags': ['survey', 'birds']}
            return SimpleNamespace(parsed={key:values[key] for key in kwargs['json_schema']['required']})
        self.model_service = SimpleNamespace(acomplete_structured=complete)
        setattr(self.ctx, 'llm', self.model_service)
        self.api = plugin._service()
        self.api.bind_generation(SimpleNamespace(llm=self.model_service, on_unload=self.disposals.append))

    async def asyncTearDown(self):
        for dispose in self.disposals:
            dispose()
        await super().asyncTearDown()

    async def press(self, label, message=None):
        button = next(b for b in self.buttons() if b['text'] == label)
        panel = next(reversed(self.controller.panels.values()))
        await self.app.process_update(self.callback_update(button['callback_data'],
            message=message or int(panel.message)))

    async def test_add_generates_missing_details_with_bounded_public_model_and_keeps_typed_values(self):
        (self.home/'workspaces/new.md').write_text('Meadow survey: three swallows.')
        # Materialize a native row without importing the host chat bootstrap:
        # its user-row classifier otherwise tries an environment relaunch in tests.
        row = self.db.append_message('fictional-session', 'assistant', 'Prepare our meadow survey.')
        import sqlite3
        with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
            conn.execute("UPDATE messages SET role='user' WHERE id=?", (row,))
        self.deliver('new.md')
        self.db.append_message('fictional-session', 'assistant', 'FUTURE PRIVATE QUESTION')
        result = await self.command('add My typed title #Keep-Case')
        self.assertEqual(result, 'Saved to Delivery Shelf: My typed title')
        item = self.store.search(q='My typed title')['items'][0]
        self.assertEqual(item['description'], 'Three swallows recorded in the meadow.')
        self.assertEqual(item['tags'], ['Keep-Case'])
        self.assertEqual(len(self.model_calls), 1)
        call = self.model_calls[0]
        self.assertEqual(call['purpose'], 'shelf.generate-details')
        self.assertLessEqual(call['max_tokens'], 1600)
        self.assertIn('three swallows', str(call['input']))
        self.assertNotIn('FUTURE PRIVATE', str(call['input']))
        self.assertNotIn('tools', call)
        self.assertEqual(self.ctx.queued, [])
    async def test_add_view_send_uses_managed_copy_after_source_removed(self):
        payload = b'Exact durable copy: meadow survey\x00bytes'
        (self.home/'workspaces/new.md').write_bytes(payload)
        self.deliver('new.md')
        result = await self.command('add Saved bytes #Exact --description "Typed description"')
        self.assertEqual(result, 'Saved to Delivery Shelf: Saved bytes')
        saved = self.store.search(q='Saved bytes')['items'][0]
        self.assertTrue(saved.get('versions'), saved)
        (self.home/'workspaces/new.md').unlink()
        await self.command('search Saved bytes')
        await self.press('Saved bytes')
        with patch.object(self.ctx, 'inject_message', side_effect=AssertionError('No agent')):
            await self.press('Send file')
        self.assertEqual(len(self.capture.uploads), 1, self.capture.calls[-1])
        self.assertEqual(self.capture.uploads[0][2]['document'][1], payload)
        self.assertEqual(self.model_calls, [])
    async def test_multiple_files_old_versions_and_explicit_add_version_approval(self):
        first = b'Original first bytes'
        second = b'Original second bytes'
        (self.home/'workspaces/new.md').write_bytes(first)
        (self.home/'workspaces/third.md').write_bytes(second)
        item = self.store.create(self.api.EntryInput(title='Multi-file report', description='Keep me', tags=['Keep'],
            files=[{'root':'workspaces','path':'new.md'}, {'root':'workspaces','path':'third.md'}]))
        await self.command('search Multi-file')
        await self.press('Multi-file report')
        await self.press('Versions')
        self.assertIn('Version 1', [b['text'] for b in self.buttons()])
        await self.press('Version 1')
        await self.press('Send all files')
        self.assertEqual([u[2]['document'][1] for u in self.capture.uploads], [first, second])
        self.deliver('old.md')
        await self.command('search Multi-file')
        await self.press('Multi-file report')
        await self.press('Add version')
        self.assertIn('Confirm new version', [b['text'] for b in self.buttons()])
        self.assertEqual(self.store.get(item['id']), item)
        await self.press('Confirm new version')
        updated = self.store.get(item['id'])
        self.assertEqual(len(updated['versions']), 2)
        self.assertEqual(updated['revision'], item['revision'] + 1)
        for key in ('title','description','tags'):
            self.assertEqual(updated[key], item[key])
        await self.press('View saved file')
        await self.press('Versions')
        await self.press('Version 1')
        (self.home/'workspaces/new.md').unlink()
        (self.home/'workspaces/third.md').unlink()
        await self.press('Send all files')
        self.assertEqual([u[2]['document'][1] for u in self.capture.uploads[-2:]], [first, second])
        self.assertEqual(self.model_calls, [])
    async def test_chooser_generates_only_selected_exact_recent_file(self):
        self.request_context()
        (self.home/'workspaces/new.md').write_text('IGNORE THIS unrelated first candidate')
        (self.home/'workspaces/third.md').write_text('SELECTED meadow field notes')
        self.deliver('new.md', 'third.md')
        self.assertIsNone(await self.controller._add_recent_panel(self.identity, 'Exact choice', self.controller.epoch))
        self.assertEqual(self.model_calls, [])
        await self.press('third.md')
        item = self.store.search(q='Exact choice')['items'][0]
        self.assertEqual(item['file']['path'], 'third.md')
        self.assertIn('SELECTED meadow', str(self.model_calls[0]['input']))
        # History contains the reference, never the unselected file's body.
        self.assertNotIn('IGNORE THIS', str(self.model_calls[0]['input']))
        self.assertEqual(item['description'], 'Three swallows recorded in the meadow.')
        self.assertEqual(self.ctx.queued, [])

    def request_context(self):
        import sqlite3
        row = self.db.append_message('fictional-session', 'assistant', 'Prepare the meadow survey report.')
        with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
            conn.execute("UPDATE messages SET role='user' WHERE id=?", (row,))

    async def test_model_failures_never_copy_or_claim_success(self):
        self.request_context()
        self.deliver('new.md')
        before = self.store.search()
        for failure in ('exception', 'invalid'):
            async def broken(**kwargs):
                if failure == 'exception':
                    raise RuntimeError('Fictional provider refusal')
                return SimpleNamespace(parsed={'title': 'Bad', 'tags': [], 'description': '', 'file':'invented'})
            self.model_service.acomplete_structured = broken
            result = await self.command('add Typed title')
            self.assertIn('not saved', result)
            self.assertEqual(self.store.search(), before)
            self.assertEqual(self.controller.panels, {})
        self.assertEqual(self.ctx.queued, [])

    async def test_typed_empty_description_and_all_metadata_bypass_generation(self):
        self.deliver('new.md')
        self.model_service.acomplete_structured = None
        self.assertEqual(await self.command('add Exact title #Typed --description ""'), 'Saved to Delivery Shelf: Exact title')
        item = self.store.search(q='Exact title')['items'][0]
        self.assertEqual((item['description'], item['tags']), ('', ['Typed']))
        self.assertEqual(self.model_calls, [])

    async def test_generation_revalidates_owner_reset_file_and_profile(self):
        for change in ('owner', 'reset', 'file', 'profile'):
            with self.subTest(change=change):
                self.request_context()
                self.deliver('new.md')
                before = self.store.search()
                entered, release = asyncio.Event(), asyncio.Event()
                original = self.model_service.acomplete_structured
                async def delayed(**kwargs):
                    entered.set()
                    await release.wait()
                    return SimpleNamespace(parsed={'title':'Must not save','description':'Stale','tags':['stale']})
                self.model_service.acomplete_structured = delayed
                current_home = [self.home]
                with patch.object(self.api, 'bound_home', side_effect=lambda: current_home[0]):
                    task = asyncio.create_task(self.command())
                    try:
                        await asyncio.wait_for(entered.wait(), 2)
                        if change == 'owner':
                            self.policy.write_text('[]')
                        elif change == 'reset':
                            self.controller.boundary(reset=True, old_session_id='fictional-session', session_id='new-session')
                        elif change == 'file':
                            (self.home/'workspaces/new.md').write_text('Changed during model inference')
                        else:
                            current_home[0] = self.home/'foreign'
                        release.set()
                        result = await asyncio.wait_for(task, 3)
                        self.assertTrue(result)
                        self.assertNotIn('Saved to', result)
                    finally:
                        release.set()
                        await asyncio.gather(task, return_exceptions=True)
                self.assertEqual(self.store.search(), before)
                self.controller.retired_sessions.clear()
                self.policy.write_text('["17"]')
                self.model_service.acomplete_structured = original

    async def test_new_version_cancel_replay_and_changed_file_do_not_overwrite(self):
        self.deliver('new.md', 'third.md')
        await self.command('search Fictional')
        await self.press('Fictional report')
        await self.press('Add version')
        await self.press('third.md')
        choices = self.buttons()
        approval = choices[0]['callback_data']
        message = int(next(reversed(self.controller.panels.values())).message)
        await self.press('Cancel')
        await self.app.process_update(self.callback_update(approval, message=message))
        self.assertTrue(self.capture.calls[-1][1].get('show_alert'))
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        await self.command('search Fictional')
        await self.press('Fictional report')
        await self.press('Add version')
        await self.press('Use all recent files')
        (self.home/'workspaces/third.md').write_text('Changed after explicit preview')
        await self.press('Confirm new version')
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        self.assertNotIn('New version saved', self.capture.calls[-1][1].get('text', ''))
    async def test_copy_failure_returns_honest_error_and_no_success(self):
        self.deliver('new.md')
        before = self.store.search()
        with patch.object(self.api.Store, 'copy_version', side_effect=OSError('Fictional storage failure')):
            result = await self.command('add Exact #Typed --description "Complete metadata"')
        self.assertIsInstance(result, str)
        self.assertNotIn('Saved to', result)
        self.assertEqual(self.store.search(), before)
        self.assertEqual(self.controller.panels, {})
    async def test_new_add_button_does_not_reuse_prior_typed_metadata(self):
        self.request_context()
        self.deliver('new.md')
        await self.command('add Prior title #Prior --description "Prior description"')
        await self.command('search Prior title')
        await self.press('Prior title')
        self.deliver('third.md')
        await self.press('Add')
        saved = self.store.search(q='Meadow survey')['items']
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['file']['path'], 'third.md')
        self.assertEqual(len(self.model_calls), 1)
    async def test_add_all_recent_files_copies_exact_set_and_generates_real_details(self):
        self.request_context()
        self.deliver('new.md', 'third.md')
        await self.command('add Collection title #Typed')
        item = self.store.search(q='Collection title')['items'][0]
        self.assertEqual([ref['path'] for ref in item['files']], ['new.md', 'third.md'])
        self.assertEqual(len(item['versions'][0]['files']), 2)
        self.assertEqual(len(self.model_calls), 2)
        self.assertEqual(item['tags'], ['Typed'])
        self.assertIn('Three swallows recorded', item['description'])
        (self.home/'workspaces/new.md').unlink()
        (self.home/'workspaces/third.md').unlink()
        await self.command('search Collection title')
        await self.press('Collection title')
        await self.press('Send all files')
        self.assertEqual([u[2]['document'][1] for u in self.capture.uploads], [b'Fictional output'] * 2)
    async def test_saved_download_rechecks_owner_after_bounded_read(self):
        self.deliver('new.md')
        await self.command('add Owned #Typed --description "Owned copy"')
        await self.command('search Owned')
        await self.press('Owned')
        read = self.controller._file_snapshot
        def revoked(selection):
            result = read(selection)
            self.policy.write_text('[]')
            return result
        with patch.object(self.controller, '_file_snapshot', revoked):
            await self.press('Send file')
        self.assertEqual(self.capture.uploads, [])

    async def test_same_path_add_never_silently_versions_changed_source(self):
        self.deliver('old.md')
        (self.home/'workspaces/old.md').write_text('Different new bytes at the original path')
        await self.command('add Not applied #Not --description "Not applied"')
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        await self.command('search '+self.entry['title'])
        await self.press(self.entry['title'])
        await self.press('Add version')
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        await self.press('Confirm new version')
        updated = self.store.get(self.entry['id'])
        self.assertEqual(len(updated['versions']), 2)
        self.assertEqual(updated['title'], self.entry['title'])
        await self.command('search '+self.entry['title'])
        await self.press(self.entry['title'])
        await self.press('Versions')
        await self.press('Version 1')
        await self.press('Send file')
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'Fictional output')

    async def test_cancel_during_model_generation_never_commits(self):
        self.request_context()
        self.deliver('new.md')
        entered, release = asyncio.Event(), asyncio.Event()
        finished = __import__('threading').Event()
        async def delayed(**kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(parsed={'title':'Cancelled','description':'Must not save','tags':['cancel']})
        self.model_service.acomplete_structured = delayed
        original = self.controller._prepare_text_add
        def observed(*args):
            try:
                return original(*args)
            finally:
                finished.set()
        with patch.object(self.controller, '_prepare_text_add', observed):
            task = asyncio.create_task(self.command())
            try:
                await asyncio.wait_for(entered.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                release.set()
                self.assertTrue(await asyncio.to_thread(finished.wait, 3))
                self.assertEqual(self.store.search()['total'], 1)
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)


# Inherited capture setup/helpers only. Legacy filename-default tests are separate.
for _name in dir(recent_transport.RecentAddTests):
    if _name.startswith('test_') and _name not in ManagedTelegramTests.__dict__:
        setattr(ManagedTelegramTests, _name, None)

class NativeManagedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_loader_adapter_gateway_dispatch_and_public_llm_capture(self):
        import os
        import tempfile
        from pathlib import Path
        from datetime import datetime, timezone
        from unittest.mock import PropertyMock
        # Importing GatewayRunner normally prepares the live installation. The
        # fixture uses already installed dependencies and must never run repair.
        with patch('hermes_cli.venv_sync.prepare_launch', return_value=None), \
             patch('pm.environments.activate_dependencies'), \
             patch('hermes_cli._early_recovery.recover_if_needed'):
            from native_telegram import prepare
            from native_telegram_lifecycle import ForumRunner
            from hermes_cli.plugins import PluginManager, PluginContext
            from plugins.platforms.telegram.adapter import TelegramAdapter
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        from hermes_state import SessionDB
        from gateway.config import Platform, PlatformConfig
        from gateway.session import SessionSource, build_session_key
        from telegram import Update
        from telegram.ext import Application
        from test_telegram import Capture
        from tools.registry import registry
        import sqlite3
        with tempfile.TemporaryDirectory(prefix='shelf-native-managed-', dir=os.environ.get('TMPDIR')) as directory:
            home = Path(directory)/'home'
            prepare(home)
            (home/'config.yaml').write_text('plugins:\n  enabled: [delivery-shelf]\n  isolation: in_process\n'
                '  entries:\n    delivery-shelf:\n      allow_gateway_injection: false\n')
            bound = set_hermes_home_override(home)
            manager = PluginManager(str(home))
            app = db = None
            calls = []
            async def complete(**kwargs):
                calls.append(kwargs)
                values = {'title':'Native model title','description':'Native structured suggestion','tags':['native']}
                return SimpleNamespace(parsed={key:values[key] for key in kwargs['json_schema']['required']})
            try:
                with patch.object(PluginContext, 'llm', new_callable=PropertyMock,
                                  return_value=SimpleNamespace(acomplete_structured=complete)), \
                     patch.object(PluginContext, 'inject_message', side_effect=AssertionError('No handoff')):
                    await asyncio.to_thread(manager.discover_and_load)
                    info = [p for p in manager.list_plugins() if p['name'] == 'delivery-shelf']
                    self.assertEqual(len(info), 1)
                    self.assertFalse(info[0]['error'], info)
                    capture = Capture()
                    app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(capture).updater(None).build()
                    await app.initialize()
                    adapter = TelegramAdapter(PlatformConfig())
                    with patch('hermes_cli.plugins.get_plugin_manager', return_value=manager):
                        adapter._wire_plugin_handlers(app)
                    controller = manager.get_platform_handler_factories('telegram')[0][0].__self__
                    handler = manager._plugin_commands['shelf']['handler']
                    search_entry = registry.get_entry('delivery_shelf_search', scope=manager.scope_key)
                    assert search_entry is not None
                    search = search_entry.handler
                    runner = ForumRunner()
                    runner.profile = controller.profile
                    source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100', chat_type='group',
                        user_id='17', thread_id='9', message_id='22', profile='default')
                    now = datetime.now(timezone.utc)
                    session = SimpleNamespace(session_id='native-managed', session_key=build_session_key(source),
                                              created_at=now, updated_at=now)
                    db = SessionDB(home/'state.db')
                    db.create_session(session.session_id, source='telegram', user_id='18')
                    row = db.append_message(session.session_id, 'assistant', 'Prepare native meadow report')
                    with closing(sqlite3.connect(home/'state.db')) as conn, conn:
                        conn.execute("UPDATE messages SET role='user' WHERE id=?", (row,))
                    payload = b'Native managed exact bytes: three swallows'
                    (home/'workspaces/first.md').write_bytes(payload)
                    db.append_message(session.session_id, 'assistant', 'MEDIA:'+str(home/'workspaces/first.md'))
                    result = await runner._hm_run_plugin_handler(handler, None, source, session_entry=session, args='add Typed native title')
                    self.assertEqual(result, 'Saved to Delivery Shelf: Typed native title')
                    saved = json.loads(search({}))['data']['items'][0]
                    self.assertEqual((saved['title'], saved['description']), ('Typed native title','Native structured suggestion'))
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0]['task'], controller.api.GENERATION_TASK)
                    (home/'workspaces/first.md').unlink()
                    async def press(label):
                        buttons = [b for row in capture.calls[-1][1]['reply_markup']['inline_keyboard'] for b in row]
                        data = next(b['callback_data'] for b in buttons if b['text'] == label)
                        panel = next(reversed(controller.panels.values()))
                        await app.process_update(Update.de_json({'update_id':1,'callback_query':{
                            'id':'native-managed','from':{'id':17,'is_bot':False,'first_name':'Fixture'},
                            'chat_instance':'fixture','data':data,'message':{'message_id':int(panel.message),'date':1,
                            'message_thread_id':9,'chat':{'id':-100,'type':'supergroup'},'text':'Shelf'}}}, app.bot))
                    await runner._hm_run_plugin_handler(handler, None, source, session_entry=session, args='')
                    await press('Typed native title')
                    await press('Send file')
                    self.assertEqual(len(capture.uploads), 1)
                    self.assertEqual(capture.uploads[0][2]['document'][1], payload)
                    self.assertEqual(capture.uploads[0][1]['message_thread_id'], 9)
                    self.assertEqual(len(calls), 1, 'Retrieval must not call the model')
            finally:
                if db is not None:
                    db.close()
                manager.unload()
                if app is not None:
                    await app.shutdown()
                reset_hermes_home_override(bound)


if __name__ == '__main__':
    unittest.main()
