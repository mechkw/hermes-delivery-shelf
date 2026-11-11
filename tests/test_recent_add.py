"""Deterministic Add at native command/PTB and read-only source boundaries."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest

import test_telegram as transport
plugin = transport.plugin
from hermes_state import SessionDB


class RecentAddTests(transport.TelegramTests):
    # Inherit only transport setup, not the legacy assisted-add expectations.
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.source.chat_id = '-100'
        self.identity = self.controller.identity(self.source, 'fictional-session', 'telegram:-100:9', 'telegram')
        self.db = SessionDB(self.home/'state.db')
        self.db.create_session('fictional-session', source='telegram')
        request = self.db.append_message('fictional-session', 'assistant', 'Prepare the fictional report.')
        with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
            conn.execute("UPDATE messages SET role='user' WHERE id=?", (request,))
        self.ctx.accept = False
        self.disposals = []
        async def complete(**kwargs):
            header = next(json.loads(block['text']) for block in kwargs['input']
                          if block.get('type') == 'text' and block.get('text', '').startswith('{"file_name"'))
            values = {'title': header['file_name'], 'description': 'Fictional file details', 'tags': ['Fixture']}
            return SimpleNamespace(parsed={key: values[key] for key in kwargs['json_schema']['required']})
        model = SimpleNamespace(acomplete_structured=complete)
        setattr(self.ctx, 'llm', model)
        plugin._service().bind_generation(SimpleNamespace(llm=model, on_unload=self.disposals.append))

    async def asyncTearDown(self):
        for dispose in self.disposals:
            dispose()
        self.db.close()
        await super().asyncTearDown()

    def deliver(self, *names):
        return self.db.append_message('fictional-session', 'assistant', '\n'.join(
            'MEDIA:' + str(self.home/'workspaces'/name) for name in names))

    async def command(self, args='add'):
        result = self.ctx.commands['shelf'](args, source=self.source, session_id='fictional-session',
            session_key='telegram:-100:9', platform='telegram')
        return await result if hasattr(result, '__await__') else result

    async def manual(self, raw=''):
        # The panel's explicit Add action remains a chooser. Typed add is quick capture.
        return await self.controller._add_recent_panel(self.identity, raw, self.controller.epoch)

    def callback_update(self, data, *, user=17, thread=9, message=None):
        from telegram import Update
        return Update.de_json({'update_id':1, 'callback_query':{
            'id':'recent-callback', 'from':{'id':user,'is_bot':False,'first_name':'Fixture'},
            'chat_instance':'fixture','data':data,
            'message':{'message_id':message or self.capture.serial,'date':1,'message_thread_id':thread,
                       'chat':{'id':-100,'type':'supergroup'},'text':'Shelf'}}}, self.app.bot)

    def buttons(self):
        return [button for row in self.capture.calls[-1][1]['reply_markup']['inline_keyboard'] for button in row]

    async def test_newest_set_chooser_selects_exact_file_and_rejects_foreign_callbacks(self):
        self.deliver('old.md')
        self.deliver('new.md', 'third.md')
        await self.manual('Chosen title #Keep-Case --description "Supplied description"')
        buttons = self.buttons()
        self.assertEqual([b['text'] for b in buttons], ['new.md','third.md','Save all 2 files','Cancel'])
        self.assertEqual(self.store.search()['total'], 1)  # only pre-existing fixture
        selected = buttons[1]['callback_data']
        message = self.capture.serial
        for who, topic in ((18,9), (17,10)):
            await self.app.process_update(self.callback_update(selected, user=who, thread=topic, message=message))
            self.assertTrue(self.capture.calls[-1][1]['show_alert'])
            self.assertEqual(self.store.search()['total'], 1)
        await self.app.process_update(self.callback_update(selected, message=message))
        saved = self.store.search(q='Chosen title')['items'][0]
        self.assertEqual(saved['file']['path'], 'third.md')
        self.assertEqual(saved['tags'], ['Keep-Case'])
        self.assertEqual(saved['description'], 'Supplied description')
        await self.app.process_update(self.callback_update(selected, message=message))
        self.assertTrue(self.capture.calls[-1][1]['show_alert'])
        self.assertEqual(self.store.search()['total'], 2)
        self.assertEqual(self.ctx.queued, [])

    async def test_rejected_replacement_and_error_edit_never_retarget_old_choice(self):
        self.deliver('old.md', 'new.md')
        await self.manual()
        old_choice = self.buttons()[1]['callback_data']
        message = self.capture.serial
        await self.app.process_update(self.callback_update(old_choice, message=message))
        view = self.buttons()[0]['callback_data']
        await self.app.process_update(self.callback_update(view, message=message))
        add = self.buttons()[0]['callback_data']
        self.deliver('old.md', 'third.md')
        before = self.store.search()
        start = len(self.capture.calls)
        self.capture.fail.add('editMessageText')
        await self.app.process_update(self.callback_update(add, message=message))
        rejected = [data for verb, data in self.capture.calls[start:] if verb == 'editMessageText']
        self.assertEqual(len(rejected), 2)  # chooser AND error confirmation rejected
        unpublished = rejected[0]['reply_markup']['inline_keyboard'][1][0]['callback_data']
        self.capture.fail.clear()
        for stale in (old_choice, unpublished):
            await self.app.process_update(self.callback_update(stale, message=message))
            self.assertTrue(self.capture.calls[-1][1].get('show_alert'), stale)
            self.assertEqual(self.store.search(), before)
        # A new command is a clean retry, not a resurrection of the rejected panel.
        await self.manual()
        retry = self.buttons()[1]['callback_data']
        self.assertNotIn(retry, (old_choice, unpublished))
        self.assertLessEqual(len(retry.encode()), 64)
        await self.app.process_update(self.callback_update(retry, message=self.capture.serial))
        self.assertEqual(self.store.search(q='third.md')['items'][0]['file']['path'], 'third.md')
        self.assertEqual(self.ctx.queued, [])

    async def test_edit_publication_requires_ack_and_fences_cancellation_or_ambiguity(self):
        from unittest.mock import patch
        from telegram.error import TimedOut
        # A rejected request and a lost/invalid acknowledgement must both fail closed.
        for outcome in ('cancel', 'timeout', 'true', 'wrong-message', 'wrong-chat', 'wrong-topic'):
            with self.subTest(outcome=outcome):
                self.deliver('old.md', 'new.md')
                await self.manual()
                old_choice = self.buttons()[1]['callback_data']
                message = self.capture.serial
                await self.app.process_update(self.callback_update(old_choice, message=message))
                await self.app.process_update(self.callback_update(self.buttons()[0]['callback_data'], message=message))
                add = self.buttons()[0]['callback_data']
                self.deliver('old.md', 'third.md')
                before = self.store.search()
                entered, release = asyncio.Event(), asyncio.Event()
                real_request = self.capture.do_request
                unpublished = []
                async def delayed(url, method, request_data=None, **kwargs):
                    data = request_data.parameters if request_data else {}
                    response = await real_request(url, method, request_data=request_data, **kwargs)
                    if url.endswith('/editMessageText') and data.get('text') == 'Shelf · Choose a file to save':
                        unpublished.extend(b['callback_data'] for row in data['reply_markup']['inline_keyboard'] for b in row)
                        entered.set()
                        await release.wait()
                        if outcome == 'timeout':
                            raise TimedOut('Fictional lost acknowledgement')
                        body = json.loads(response[1])
                        if outcome == 'true':
                            body['result'] = True
                        elif outcome == 'wrong-message':
                            body['result']['message_id'] += 1
                        elif outcome == 'wrong-chat':
                            body['result']['chat']['id'] = -101
                        elif outcome == 'wrong-topic':
                            body['result']['message_thread_id'] = 10
                        return 200, json.dumps(body).encode()
                    return response
                with patch.object(self.capture, 'do_request', delayed):
                    task = asyncio.create_task(self.app.process_update(self.callback_update(add, message=message)))
                    try:
                        await asyncio.wait_for(entered.wait(), 2)
                        self.assertNotIn(old_choice, unpublished)
                        for data in (old_choice, unpublished[1]):
                            await self.app.process_update(self.callback_update(data, message=message))
                            self.assertTrue(self.capture.calls[-1][1].get('show_alert'))
                            self.assertEqual(self.store.search(), before)
                        if outcome == 'cancel':
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                        else:
                            release.set()
                            await task
                    finally:
                        release.set()
                        if not task.done():
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                for data in (old_choice, unpublished[1]):
                    await self.app.process_update(self.callback_update(data, message=message))
                    self.assertTrue(self.capture.calls[-1][1].get('show_alert'))
                    self.assertEqual(self.store.search(), before)
                # Retry presents current choices; a genuine Cancel remains harmless.
                await self.manual()
                retry_buttons, retry_message = self.buttons(), self.capture.serial
                await self.app.process_update(self.callback_update(retry_buttons[-1]['callback_data'], message=retry_message))
                self.assertIn('Cancelled', self.capture.calls[-1][1]['text'])
                self.assertEqual(self.store.search(), before)
        await self.manual()
        await self.app.process_update(self.callback_update(self.buttons()[1]['callback_data'], message=self.capture.serial))
        self.assertEqual(self.store.search(q='third.md')['total'], 1)

    async def test_successful_replacements_never_reuse_old_choice_tokens(self):
        self.deliver('old.md', 'new.md')
        await self.manual()
        message = self.capture.serial
        old_choices = [b['callback_data'] for b in self.buttons()]
        await self.app.process_update(self.callback_update(old_choices[1], message=message))
        for _ in range(12):
            await self.app.process_update(self.callback_update(self.buttons()[0]['callback_data'], message=message))
            self.deliver('old.md', 'third.md')
            await self.app.process_update(self.callback_update(self.buttons()[0]['callback_data'], message=message))
            choices = [b['callback_data'] for b in self.buttons()]
            self.assertFalse(set(choices) & set(old_choices))
            self.assertTrue(all(len(data.encode()) <= 64 for data in choices))
            before = self.store.search()
            for stale in old_choices:
                await self.app.process_update(self.callback_update(stale, message=message))
                self.assertTrue(self.capture.calls[-1][1].get('show_alert'))
            self.assertEqual(self.store.search(), before)
            old_choices.extend(choices)
            await self.app.process_update(self.callback_update(choices[1], message=message))
            self.assertEqual(self.store.search(q='third.md')['total'], 1)
        self.assertEqual(self.ctx.queued, [])

    async def test_duplicate_keeps_existing_metadata_revision_and_exposes_view(self):
        self.deliver('old.md')
        await self.manual('Replacement #Not-used --description "Not used"')
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        self.assertEqual(self.store.search()['total'], 1)
        self.assertIn('Already saved', self.capture.calls[-1][1]['text'])
        self.assertEqual(self.buttons()[0]['text'], 'View saved file')

    async def test_missing_never_offers_unsupported_reply_or_injection(self):
        result = await self.manual()
        self.assertEqual(result, 'No recent file found. Ask me to save the file in normal chat.')
        self.assertEqual(self.ctx.queued, [])

    async def test_changed_source_and_reset_and_expired_chooser_never_save(self):
        import time
        for change in ('source', 'reset', 'expired', 'policy'):
            with self.subTest(change=change):
                row = self.deliver('new.md', 'third.md')
                await self.manual()
                button = self.buttons()[0]['callback_data']
                message = self.capture.serial
                panel = next(reversed(self.controller.panels.values()))
                if change == 'source':
                    with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
                        conn.execute('UPDATE messages SET content=? WHERE id=?', ('Changed', row))
                elif change == 'expired':
                    panel.expires = time.monotonic()-1
                elif change == 'policy':
                    self.policy.write_text('[]')
                else:
                    self.controller.boundary(reset=True, old_session_id='fictional-session', session_id='fresh')
                await self.app.process_update(self.callback_update(button, message=message))
                self.assertEqual(self.store.search()['total'], 1)
                self.controller.retired_sessions.clear()  # new independent fixture iteration
                self.policy.write_text('["17"]')

    async def test_source_excludes_tools_users_other_sessions_and_prose(self):
        path = str(self.home/'workspaces/new.md')
        self.db.create_session('other-session', source='telegram')
        self.db.append_message('other-session', 'assistant', 'MEDIA:'+path)
        self.db.append_message('fictional-session', 'tool', 'MEDIA:'+path)
        self.db.append_message('fictional-session', 'user', 'MEDIA:'+path)
        self.db.append_message('fictional-session', 'assistant', 'Here is a possible path: '+path)
        self.db.append_message('fictional-session', 'assistant', '```text\nMEDIA:'+path+'\n```')
        result = await self.manual()
        self.assertIn('No recent file found', result)
        self.assertEqual(self.store.search()['total'], 1)

    async def test_native_rich_text_blob_and_retained_null_indices_are_read_only(self):
        self.db.append_message('fictional-session', 'assistant', [
            {'type':'thinking','thinking':'MEDIA:'+str(self.home/'workspaces/third.md')},
            {'type':'text','text':'MEDIA:'+str(self.home/'workspaces/new.md')}])
        # Native display materialization produces the real BLOB shape.
        self.db.get_messages('fictional-session', include_compacted=True)
        with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
            self.assertEqual(conn.execute('SELECT typeof(display_identity) FROM messages LIMIT 1').fetchone()[0], 'blob')
        for legacy in (False, True):
            if legacy:
                with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
                    conn.execute('UPDATE messages SET display_order=NULL,display_identity=NULL')
            with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
                before = list(conn.iterdump())
            await self.manual()
            with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
                self.assertEqual(list(conn.iterdump()), before)
            self.assertEqual(self.store.search()['total'], 2)
        self.assertEqual(self.ctx.queued, [])

    async def test_unsupported_or_missing_newest_file_does_not_save_stale_older_delivery(self):
        self.deliver('old.md')
        for name in ('not-there.md', 'unsupported.exe', '.env', 'secret.md'):
            with self.subTest(name=name):
                self.deliver(name)
                result = await self.manual()
                self.assertTrue(result)
                self.assertNotIn('Already saved', result)
                self.assertEqual(self.store.search()['total'], 1)

    async def test_panel_add_and_cancel_are_direct_and_cancel_does_not_save(self):
        self.deliver('new.md', 'third.md')
        await self.command('')
        add = self.buttons()[0]
        self.assertEqual(add['text'], 'Add')
        await self.app.process_update(self.callback_update(add['callback_data']))
        cancel = self.buttons()[-1]
        # editMessageText capture increments its serial but the panel message is unchanged.
        panel = next(reversed(self.controller.panels.values()))
        await self.app.process_update(self.callback_update(cancel['callback_data'], message=int(panel.message)))
        self.assertIn('Cancelled', self.capture.calls[-1][1]['text'])
        self.assertEqual(self.store.search()['total'], 1)
        self.assertEqual(self.ctx.queued, [])

    async def test_cancelled_command_waiting_for_catalog_never_commits(self):
        import threading
        from contextlib import contextmanager
        from unittest.mock import patch
        self.deliver('new.md')
        lock = sqlite3.connect(self.store.path)
        lock.execute('BEGIN IMMEDIATE')
        entered, finished = threading.Event(), threading.Event()
        Store = plugin._service().Store
        original = Store.connect
        @contextmanager
        def traced(store):
            with original(store) as conn:
                conn.set_trace_callback(lambda sql: entered.set() if sql == 'BEGIN IMMEDIATE' else None)
                yield conn
        prepare = self.controller._prepare_recent
        def observed(*args):
            try:
                return prepare(*args)
            finally:
                finished.set()
        try:
            with patch.object(Store, 'connect', traced), patch.object(self.controller, '_prepare_recent', observed):
                task = asyncio.create_task(self.manual())
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                lock.rollback()
                self.assertTrue(await asyncio.to_thread(finished.wait, 2))
            self.assertEqual(self.store.search()['total'], 1)
        finally:
            lock.close()

    async def test_catalog_wait_rechecks_home_before_any_source_read(self):
        import importlib
        import threading
        from contextlib import contextmanager
        from unittest.mock import patch
        self.deliver('new.md')
        api = plugin._service()
        source = importlib.import_module(plugin.__name__ + '.recent_artifacts')
        current_home = [self.home]
        entered = threading.Event()
        original_connect = api.Store.connect
        original_source = source.connection
        reads = []
        @contextmanager
        def traced(store):
            with original_connect(store) as conn:
                conn.set_trace_callback(lambda sql: entered.set() if sql == 'BEGIN IMMEDIATE' else None)
                yield conn
        @contextmanager
        def traced_source(home):
            with original_source(home) as conn:
                conn.set_trace_callback(lambda sql: reads.append((current_home[0], sql)))
                yield conn
        lock = sqlite3.connect(self.store.path)
        lock.execute('BEGIN IMMEDIATE')
        try:
            with patch.object(api.Store, 'connect', traced), patch.object(source, 'connection', traced_source), \
                    patch.object(source, 'candidates', wraps=source.candidates) as candidates, \
                    patch.object(api, 'bound_home', side_effect=lambda: current_home[0]):
                task = asyncio.create_task(self.manual())
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                self.assertFalse(task.done())
                before, candidate_calls = list(reads), candidates.call_count
                self.assertTrue(before)
                current_home[0] = self.home/'foreign-profile'
                lock.rollback()
                result = await asyncio.wait_for(task, 3)
                self.assertEqual(reads, before, 'No source SQL may run after the bound home changes')
                self.assertEqual(candidates.call_count, candidate_calls)
                self.assertIn('session changed', result)
            self.assertEqual(self.store.search()['total'], 1)
        finally:
            lock.close()

    async def test_final_guard_rechecks_home_after_blocking_candidate_reads(self):
        import importlib
        import threading
        from unittest.mock import patch
        self.deliver('new.md')
        api = plugin._service()
        source = importlib.import_module(plugin.__name__ + '.recent_artifacts')
        current_home = [self.home]
        entered, release = threading.Event(), threading.Event()
        real_candidates = source.candidates
        calls = 0
        def delayed(*args):
            nonlocal calls
            result = real_candidates(*args)
            calls += 1
            if calls == 2:
                entered.set()
                if not release.wait(3):
                    raise AssertionError('Candidate-read barrier timed out')
            return result
        with patch.object(source, 'candidates', delayed), \
                patch.object(api, 'bound_home', side_effect=lambda: current_home[0]):
            task = asyncio.create_task(self.manual())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                current_home[0] = self.home/'foreign-profile'
                release.set()
                result = await asyncio.wait_for(task, 3)
                self.assertIn('session changed', result)
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(self.store.search()['total'], 1)

    async def test_duplicate_filenames_have_distinguishable_choices(self):
        for folder in ('one', 'two'):
            target = self.home/'workspaces'/folder/'result.md'
            target.parent.mkdir()
            target.write_text('Fictional file')
        self.deliver('one/result.md', 'two/result.md')
        await self.manual()
        self.assertEqual([b['text'] for b in self.buttons()], ['one/result.md', 'two/result.md', 'Save all 2 files', 'Cancel'])

    async def test_concurrent_commands_are_idempotent_without_metadata_overwrite(self):
        self.deliver('new.md')
        raw = 'add new.md #Fixture --description "Fictional file details"'
        results = await asyncio.gather(self.command(raw), self.command(raw))
        self.assertEqual(self.store.search()['total'], 2)
        saved = self.store.search(q='new.md')['items'][0]
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(sum('Already saved' in (result or '') for result in results), 1)

    async def test_missing_source_identity_never_falls_back_to_injection(self):
        result = self.ctx.commands['shelf']('add', platform='telegram', session_id='fictional-session',
                                          session_key='telegram:-100:9')
        result = await result if hasattr(result, '__await__') else result
        self.assertIn('owner policy required', result)
        self.assertEqual(self.ctx.queued, [])

    async def test_chooser_never_hydrates_or_selects_future_deliveries(self):
        self.deliver('new.md', 'third.md')
        await self.manual()
        choice = self.buttons()[0]['callback_data']
        message = self.capture.serial
        self.db.append_message('fictional-session', 'assistant', 'x'*70000+'\nMEDIA:/not/future.md')
        await self.app.process_update(self.callback_update(choice, message=message))
        self.assertEqual(self.store.search(q='new.md')['total'], 1)
        self.assertEqual(self.store.search()['total'], 2)

    async def test_foreign_profile_and_bounded_window_fail_without_scanning_older(self):
        self.deliver('new.md')
        for i in range(40):
            self.db.append_message('fictional-session', 'assistant', 'Ordinary response '+str(i))
        self.assertIn('No recent file found', await self.manual())
        self.deliver('new.md')
        with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
            conn.execute("UPDATE sessions SET profile_name='foreign' WHERE id='fictional-session'")
        self.assertIn('unavailable', await self.manual())
        self.assertEqual(self.store.search()['total'], 1)

    async def test_added_file_view_sends_exact_bytes_without_model_or_injection(self):
        from unittest.mock import Mock, patch
        payload = b'Integrated Add then download: exact bytes'
        (self.home/'workspaces/new.md').write_bytes(payload)
        self.deliver('new.md')
        reject = Mock(side_effect=AssertionError('No agent handoff'))
        model_calls = Mock(side_effect=AssertionError('No model calls for supplied metadata or download'))
        bound_model = SimpleNamespace(acomplete_structured=model_calls)
        plugin._service().bind_generation(SimpleNamespace(llm=bound_model, on_unload=self.disposals.append))
        with patch.object(self.ctx, 'inject_message', reject), patch.object(self.ctx, 'llm', reject, create=True):
            self.assertIsNone(await self.manual('new.md #Exact --description "Exact bytes"'))
            message = self.capture.serial
            view = self.buttons()[0]['callback_data']
            await self.app.process_update(self.callback_update(view, message=message))
            send = next(b['callback_data'] for b in self.buttons() if b['text'] == 'Send file')
            await self.app.process_update(self.callback_update(send, message=message))
            await self.app.process_update(self.callback_update(send, message=message))
            reject.assert_not_called()
            model_calls.assert_not_called()
        self.assertEqual(len(self.capture.uploads), 1)
        verb, data, files = self.capture.uploads[0]
        self.assertEqual((verb, data['chat_id'], data['message_thread_id']), ('sendDocument', -100, 9))
        self.assertEqual(files['document'][1], payload)
        self.assertEqual(self.store.search(q='new.md')['total'], 1)
        self.assertEqual(self.store.search(q='new.md')['items'][0]['revision'], 1)

    async def test_single_group_add_without_injection_registers_and_reads_back(self):
        self.deliver('new.md')
        result = await self.command('add new.md #Fixture --description "Fictional file details"')
        saved = self.store.search(q='new.md')['items']
        self.assertEqual(len(saved), 1, result)
        self.assertEqual(saved[0]['file'], {'root':'workspaces','path':'new.md'})
        self.assertEqual(saved[0]['session_id'], 'fictional-session')
        self.assertEqual(self.ctx.queued, [])
        self.assertIn('Saved', result or self.capture.calls[-1][1].get('text', ''))


# unittest collects inherited tests; the legacy suite is run separately.
for _name in dir(transport.TelegramTests):
    if _name.startswith('test_'):
        setattr(RecentAddTests, _name, None)

if __name__ == '__main__': unittest.main()
