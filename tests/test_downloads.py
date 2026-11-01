"""Direct retrieval through registered commands and real PTB capture transport."""
import asyncio
import json
from unittest.mock import Mock, patch
from test_telegram import TelegramTests, plugin
from hermes_cli.plugin_command_dispatch import invoke_plugin_command


class DownloadTests(TelegramTests):
    # Reuse fixture helpers, not the inherited regression test cases.
    async def test_download_button_sends_exact_file_in_forum_without_inference(self):
        self.source.chat_id = '-100'
        self.ctx.inject_message = Mock(side_effect=AssertionError('No injection'))
        self.ctx.llm = Mock(side_effect=AssertionError('No inference'))
        token = await self.panel()
        await self.click(token, '1', chat=-100)
        keyboard = self.edited()[-1]['reply_markup']['inline_keyboard']
        send = next(row[0]['callback_data'] for row in keyboard if row[0]['text'] == 'Send file')
        await self.click(token, data=send, chat=-100)
        documents = [(d, files) for verb, d, files in self.capture.uploads if verb == 'sendDocument']
        self.assertEqual(len(documents), 1)
        data, files = documents[0]
        self.assertEqual(data['chat_id'], -100)
        self.assertEqual(data['message_thread_id'], 9)
        self.assertEqual(files['document'][1], b'Fictional output')
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        self.ctx.inject_message.assert_not_called()
        self.ctx.llm.assert_not_called()
        await self.click(token, data=send, chat=-100)
        self.assertEqual(len(self.capture.uploads), 1)
    async def command(self, args, *, session_id='fictional-session', **changes):
        source = __import__('types').SimpleNamespace(**{**vars(self.source), **changes})
        result = invoke_plugin_command(self.ctx.commands['shelf'], args, source=source,
                                       session_id=session_id, session_key='telegram:17:9', platform='telegram')
        return await result if __import__('inspect').isawaitable(result) else result

    async def test_foreign_profile_list_rejected_before_query_or_metadata(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        foreign = self.home/'profiles/foreign'
        foreign.mkdir(parents=True)
        bound = set_hermes_home_override(foreign)
        try:
            with patch.object(plugin._service().Store, 'search', wraps=self.store.search) as search:
                result = await self.command('search Fictional')
                self.assertNotIn('Fictional', result)
                self.assertNotIn('matching deliveries', result)
                search.assert_not_called()
            self.assertFalse(self.capture.uploads)
        finally:
            reset_hermes_home_override(bound)

    async def test_failed_new_list_never_authorizes_unseen_number(self):
        await self.panel()
        (self.home/'workspaces/new.md').write_bytes(b'Unseen new bytes')
        self.store.create(plugin._service().EntryInput(title='Unseen new report',
            file={'root':'workspaces','path':'new.md'}))
        self.capture.fail.add('sendMessage')
        try:
            await self.command('')
        except Exception:
            pass  # The host may surface the transport failure; no mapping may change to it.
        await self.command('dl 1')
        self.assertFalse(any(files['document'][1] == b'Unseen new bytes'
                             for verb, data, files in self.capture.uploads))

    async def test_page_numbers_publish_only_after_matching_edit_receipt(self):
        (self.home/'workspaces/new.md').write_bytes(b'New page bytes')
        for i in range(5):
            self.store.create(plugin._service().EntryInput(title=f'Page entry {i}',
                file={'root':'workspaces','path':'new.md'}))
        token = await self.panel()
        browse = next(r[0]['callback_data'] for r in self.sent()[-1]['reply_markup']['inline_keyboard']
                      if r[0]['text'] == 'Browse more')
        await self.click(token, data=browse)
        self.assertIn('1. Fictional report', self.edited()[-1]['text'])
        self.assertIn('sent', await self.command('dl 1'))
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'Fictional output')

    async def test_delayed_list_read_rechecks_profile_owner_and_lifecycle(self):
        import threading
        api = plugin._service()
        for native in (False, True):
            for change in ('home', 'owner', 'boundary'):
                with self.subTest(native=native, change=change):
                    started, release = threading.Event(), threading.Event()
                    original = api.Store.search
                    current_home = [self.home]
                    def blocked(store, *args, **kwargs):
                        data = original(store, *args, **kwargs)
                        started.set()
                        if not release.wait(3): raise AssertionError('read barrier timed out')
                        return data
                    with patch.object(api, 'bound_home', side_effect=lambda: current_home[0]), \
                            patch.object(api.Store, 'search', blocked), \
                            patch.object(self.controller, 'application', self.app if native else None):
                        # Synchronous fallback must also run in the host's worker.
                        async def invoke():
                            result = await asyncio.to_thread(invoke_plugin_command, self.ctx.commands['shelf'],
                                'search Fictional', source=self.source, session_id='fictional-session',
                                session_key='telegram:17:9', platform='telegram')
                            return await result if __import__('inspect').isawaitable(result) else result
                        before = len(self.sent())
                        task = asyncio.create_task(invoke())
                        try:
                            self.assertTrue(await asyncio.to_thread(started.wait, 2))
                            if change == 'home': current_home[0] = self.home/'foreign'
                            elif change == 'owner': self.policy.write_text('[]')
                            else: self.controller.boundary(session_id='other-session')
                        finally:
                            release.set()
                        result = await asyncio.wait_for(task, 3)
                        self.assertNotIn('Fictional', result or '')
                        self.assertNotIn('matching deliveries', result or '')
                        self.assertEqual(len(self.sent()), before)
                    self.policy.write_text('["17"]')

    async def test_host_text_fallback_does_not_authorize_numbers(self):
        await self.panel()
        (self.home/'workspaces/new.md').write_bytes(b'Fallback-only bytes')
        self.store.create(plugin._service().EntryInput(title='Fallback result',
            file={'root':'workspaces','path':'new.md'}))
        with patch.object(self.controller, 'application', None):
            result = await self.command('search Fallback')
        self.assertIn('• Fallback result', result)
        self.assertNotIn('1. Fallback', result)
        self.assertIn('Numbered downloads unavailable', result)
        self.assertIn('Open /shelf', await self.command('dl 1'))
        self.assertFalse(self.capture.uploads)

    async def test_overlapping_list_commands_and_page_cannot_publish_out_of_order(self):
        token = await self.panel()
        browse = next(r[0]['callback_data'] for r in self.sent()[-1]['reply_markup']['inline_keyboard']
                      if r[0]['text'] == 'Browse more')
        (self.home/'workspaces/new.md').write_bytes(b'New acknowledged bytes')
        self.store.create(plugin._service().EntryInput(title='New acknowledged report',
            file={'root':'workspaces','path':'new.md'}))
        original = self.capture.do_request
        started, release = asyncio.Event(), asyncio.Event()
        async def blocked(url, method, **kwargs):
            if url.endswith('/sendMessage'):
                started.set()
                await release.wait()
            return await original(url, method, **kwargs)
        self.capture.do_request = blocked
        task = asyncio.create_task(self.command('search New acknowledged'))
        try:
            await asyncio.wait_for(started.wait(), 2)
            self.assertIn('progress', await self.command(''))
            await self.click(token, data=browse)
            self.assertFalse(self.edited())
            self.assertIn('Open /shelf', await self.command('dl 1'))
            self.assertFalse(self.capture.uploads)
        finally:
            release.set()
        self.assertIsNone(await task)
        self.capture.do_request = original
        self.assertIn('sent', await self.command('dl 1'))
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'New acknowledged bytes')
        self.assertEqual(len(self.sent()), 2)

    async def test_page_blocks_new_list_until_ack_and_failure_never_publishes(self):
        token = await self.panel()
        browse = next(r[0]['callback_data'] for r in self.sent()[-1]['reply_markup']['inline_keyboard']
                      if r[0]['text'] == 'Browse more')
        (self.home/'workspaces/new.md').write_bytes(b'Unseen page bytes')
        self.store.create(plugin._service().EntryInput(title='Unseen page',
            file={'root':'workspaces','path':'new.md'}))
        original = self.capture.do_request
        started, release = asyncio.Event(), asyncio.Event()
        async def blocked(url, method, **kwargs):
            if url.endswith('/editMessageText'):
                started.set()
                await release.wait()
                return 400, json.dumps({'ok':False, 'description':'Rejected page'}).encode()
            return await original(url, method, **kwargs)
        self.capture.do_request = blocked
        task = asyncio.create_task(self.click(token, data=browse))
        try:
            await asyncio.wait_for(started.wait(), 2)
            self.assertIn('progress', await self.command('search Unseen'))
            self.assertIn('Open /shelf', await self.command('dl 1'))
        finally:
            release.set()
        await task
        self.capture.do_request = original
        self.assertIn('Open /shelf', await self.command('dl 1'))
        self.assertFalse(self.capture.uploads)
        # Unknown delivery order stays fenced, but browsing and explicit Send file work.
        token = await self.panel()
        self.assertIn('Numbered downloads disabled', self.sent()[-1]['text'])
        await self.click(token, '1')
        send = next(r[0]['callback_data'] for r in self.edited()[-1]['reply_markup']['inline_keyboard']
                    if r[0]['text'] == 'Send file')
        await self.click(token, data=send)
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'Unseen page bytes')

    async def test_cancelled_preparation_cannot_overwrite_later_acknowledged_list(self):
        import threading
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        original_search = plugin._service().Store.search
        original_prepare = self.controller._prepare_send
        def blocked(store, *args, **kwargs):
            result = original_search(store, *args, **kwargs)
            if kwargs.get('q') == 'Fictional':
                started.set()
                if not release.wait(3): raise AssertionError('read barrier timed out')
            return result
        def observed(*args):
            try: return original_prepare(*args)
            finally:
                if args[-1] == 'Fictional': done.set()
        (self.home/'workspaces/new.md').write_bytes(b'Later acknowledged bytes')
        self.store.create(plugin._service().EntryInput(title='Later result',
            file={'root':'workspaces','path':'new.md'}))
        with patch.object(plugin._service().Store, 'search', blocked), \
                patch.object(self.controller, '_prepare_send', observed):
            task = asyncio.create_task(self.command('search Fictional'))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
                self.assertIsNone(await self.command('search Later'))
            finally:
                release.set()
                self.assertTrue(await asyncio.to_thread(done.wait, 2))
        self.assertIn('sent', await self.command('dl 1'))
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'Later acknowledged bytes')
        self.assertEqual(len(self.sent()), 1)

    async def test_cancelled_transport_late_ack_cannot_reenable_numbers(self):
        original = self.capture.do_request
        started, release = asyncio.Event(), asyncio.Event()
        late = []
        async def blocked(url, method, request_data=None, **kwargs):
            if url.endswith('/sendMessage') and not late:
                async def deliver_later():
                    started.set()
                    await release.wait()
                    return await original(url, method, request_data=request_data, **kwargs)
                late.append(asyncio.create_task(deliver_later()))
                return await asyncio.shield(late[0])
            return await original(url, method, request_data=request_data, **kwargs)
        self.capture.do_request = blocked
        task = asyncio.create_task(self.command(''))
        try:
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertIsNone(await self.command('search Fictional'))
            self.assertIn('Numbered downloads disabled', self.sent()[-1]['text'])
        finally:
            release.set()
            if late: await asyncio.wait_for(late[0], 2)
            self.capture.do_request = original
        self.assertIn('Open /shelf', await self.command('dl 1'))
        self.assertFalse(self.capture.uploads)

    async def test_send_and_page_receipts_must_match_text_route_message_and_lifetime(self):
        original = self.capture.do_request
        for edit in (False, True):
            for fault in ('text', 'chat', 'topic', 'message', 'expiry', 'publication_expiry', 'owner', 'home', 'boundary'):
                with self.subTest(edit=edit, fault=fault):
                    # Distinct real session contexts keep conservative uncertainty
                    # fences independent; a reconnect alone must not clear them.
                    session = f'receipt-{edit}-{fault}'
                    token = await self.panel(session_id=session)
                    browse = next(r[0]['callback_data'] for r in self.sent()[-1]['reply_markup']['inline_keyboard']
                                  if r[0]['text'] == 'Browse more')
                    current_home = [self.home]
                    async def wrong(url, method, request_data=None, **kwargs):
                        code, raw = await original(url, method, request_data=request_data, **kwargs)
                        if url.endswith('/editMessageText' if edit else '/sendMessage'):
                            body = json.loads(raw)
                            result = body['result']
                            if fault == 'text': result['text'] = 'Unrelated reply'
                            elif fault == 'chat': result['chat']['id'] = 18
                            elif fault == 'topic': result['message_thread_id'] = 10
                            elif fault == 'message': result['message_id'] = 999 if edit else 0
                            elif fault == 'expiry':
                                for p in self.controller.panels.values(): p.expires = 0
                            elif fault == 'publication_expiry':
                                for p in self.controller.publications.values(): p['expires'] = 0
                            elif fault == 'owner': self.policy.write_text('[]')
                            elif fault == 'home': current_home[0] = self.home/'foreign'
                            else: self.controller.boundary(session_id='other-session')
                            raw = json.dumps(body).encode()
                        return code, raw
                    with patch.object(plugin._service(), 'bound_home', side_effect=lambda: current_home[0]):
                        self.capture.do_request = wrong
                        try:
                            if edit: await self.click(token, data=browse)
                            else: await self.command('search Fictional', session_id=session)
                        finally:
                            self.capture.do_request = original
                    self.policy.write_text('["17"]')
                    self.assertIn('Open /shelf', await self.command('dl 1', session_id=session))
                    self.assertFalse(self.capture.uploads)

    async def test_list_publication_after_worker_authorization_fences_old_number_send(self):
        import threading
        await self.command('search Fictional')
        (self.home/'workspaces/new.md').write_bytes(b'Newer numbered bytes')
        self.store.create(plugin._service().EntryInput(title='Newer numbered report',
            file={'root':'workspaces','path':'new.md'}))
        started, release = threading.Event(), threading.Event()
        original = self.controller._download_authorized
        def blocked(*args):
            result = original(*args)
            started.set()
            if not release.wait(3): raise AssertionError('authorization barrier timed out')
            return result
        with patch.object(self.controller, '_download_authorized', blocked):
            task = asyncio.create_task(self.command('dl 1'))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertIsNone(await self.command('search Newer'))
            finally:
                release.set()
            await asyncio.wait_for(task, 3)
        self.assertFalse(self.capture.uploads)
        self.assertIn('sent', await self.command('dl 1'))
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'Newer numbered bytes')

    async def test_cancelled_page_worker_cannot_publish_or_reenable_stale_callback(self):
        import threading
        token = await self.panel()
        browse = next(r[0]['callback_data'] for r in self.sent()[-1]['reply_markup']['inline_keyboard']
                      if r[0]['text'] == 'Browse more')
        (self.home/'workspaces/new.md').write_bytes(b'New result after cancellation')
        self.store.create(plugin._service().EntryInput(title='New result',
            file={'root':'workspaces','path':'new.md'}))
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        original_search, original_perform = plugin._service().Store.search, self.controller._perform
        def blocked(store, *args, **kwargs):
            data = original_search(store, *args, **kwargs)
            if kwargs.get('q') == '':
                started.set()
                if not release.wait(3): raise AssertionError('page barrier timed out')
            return data
        def observed(*args):
            try: return original_perform(*args)
            finally: done.set()
        with patch.object(plugin._service().Store, 'search', blocked), \
                patch.object(self.controller, '_perform', observed):
            task = asyncio.create_task(self.click(token, data=browse))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
                self.assertIsNone(await self.command('search New'))
            finally:
                release.set()
                self.assertTrue(await asyncio.to_thread(done.wait, 2))
        await self.click(token, data=browse)
        self.assertFalse(self.edited())
        self.assertFalse(self.capture.uploads)
        self.assertIn('sent', await self.command('dl 1'))
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], b'New result after cancellation')

    async def test_zip_download_is_opaque_and_numbering_does_not_shift(self):
        api = plugin._service()
        content = b'PK\\x03\\x04opaque zip: never unpack me'
        (self.home/'workspaces/bundle.zip').write_bytes(content)
        with patch('zipfile.ZipFile', side_effect=AssertionError('Never extract')):
            entry = self.store.create(api.EntryInput(title='Bundle', file={'root':'workspaces','path':'bundle.zip'}))
            listing = await self.command('search Bundle')
            self.assertIsNone(listing)  # Native send owns the acknowledgement.
            self.assertIn('1. Bundle', self.sent()[-1]['text'])
            self.store.create(api.EntryInput(title='Newer', file={'root':'workspaces','path':'new.md'}))
            result = await self.command('dl 1')
            self.assertIn('sent', result)
        self.assertEqual(self.capture.uploads[-1][2]['document'][1], content)
        self.assertEqual(self.capture.uploads[-1][2]['document'][0], 'bundle.zip')
        self.assertEqual(self.store.get(entry['id']), entry)
    async def test_recent_batch_is_bounded_and_reports_missing_attachments(self):
        api = plugin._service()
        self.store.create(api.EntryInput(title='Reference only', description='/do/not/guess.zip'))
        missing = self.store.create(api.EntryInput(title='Missing', file={'root':'workspaces','path':'new.md'}))
        (self.home/'workspaces/new.md').unlink()
        result = await self.command('r3')
        self.assertIn('1 sent; 1 unavailable', result)
        self.assertIn('1 fewer attached', result)
        self.assertEqual(len(self.capture.uploads), 1)
        self.assertIn('1–5', await self.command('r6'))
        self.assertEqual(self.store.get(missing['id']), missing)
    async def test_numbered_selection_expiry_is_rechecked_after_file_read(self):
        await self.command('search Fictional')
        original = self.controller._file_snapshot
        def expire(selection):
            result = original(selection)
            for snapshot in self.controller.snapshots.values():
                snapshot['expires'] = 0
            return result
        with patch.object(self.controller, '_file_snapshot', side_effect=expire):
            result = await self.command('dl 1')
        self.assertFalse(self.capture.uploads)
        self.assertIn('/shelf', result)
    async def test_selection_isolated_expired_and_metadata_only(self):
        api = plugin._service()
        self.ctx.inject_message = Mock(side_effect=AssertionError('No injection'))
        self.ctx.llm = Mock(side_effect=AssertionError('No inference'))
        self.assertIn('Open /shelf', await self.command('dl 1'))
        await self.command('search Fictional')
        self.policy.write_text('["17", "18"]')
        for changes in ({'user_id':'18'}, {'chat_id':'18'}, {'thread_id':'10'}):
            self.assertIn('Open /shelf', await self.command('download 1', **changes))
        self.store.create(api.EntryInput(title='Reference', description='File: workspaces:old.md'))
        self.assertIsNone(await self.command('search Reference'))
        self.assertIn('no file attached', self.sent()[-1]['text'])
        self.assertIn('unavailable', await self.command('dl 1'))
        for snapshot in self.controller.snapshots.values(): snapshot['expires'] = 0
        self.assertIn('Open /shelf', await self.command('dl 1'))
        self.assertFalse(self.capture.uploads)
        self.ctx.inject_message.assert_not_called()
        self.ctx.llm.assert_not_called()

    async def send_button(self):
        token = await self.panel()
        await self.click(token, '1')
        keyboard = self.edited()[-1]['reply_markup']['inline_keyboard']
        data = next(row[0]['callback_data'] for row in keyboard if row[0]['text'] == 'Send file')
        return token, data

    async def test_download_callback_identity_and_expiry_fences(self):
        token, data = await self.send_button()
        for changes in ({'user':18}, {'chat':18}, {'thread':10}, {'message':999}, {'date':0}):
            await self.click(token, data=data, **changes)
        self.assertFalse(self.capture.uploads)
        self.controller.panels[token].expires = 0
        await self.click(token, data=data)
        self.assertFalse(self.capture.uploads)

    async def test_revision_race_never_sends_retargeted_file(self):
        token, data = await self.send_button()
        payload = {k:self.entry[k] for k in plugin._service().EntryInput.model_fields}
        original = self.controller._file_snapshot
        def change(selection):
            result = original(selection)
            self.store.update(self.entry['id'], plugin._service().EntryUpdate(**{**payload,
                'file':{'root':'workspaces','path':'new.md'}, 'revision':1}))
            return result
        with patch.object(self.controller, '_file_snapshot', side_effect=change):
            await self.click(token, data=data)
        self.assertFalse(self.capture.uploads)
        self.assertIn('changed', self.edited()[-1]['text'])

    async def test_policy_file_and_lifecycle_revocation_after_snapshot(self):
        original = self.controller._file_snapshot
        for mutation in ('replace', 'grow', 'root', 'owner', 'reset'):
            with self.subTest(mutation=mutation):
                await self.command('search Fictional')
                def change(selection):
                    result = original(selection)
                    if mutation == 'replace':
                        (self.home/'workspaces/old.md').unlink()
                        (self.home/'workspaces/old.md').write_text('wrong bytes')
                    elif mutation == 'grow':
                        (self.home/'workspaces/old.md').write_bytes(b'x' * (plugin._service().MAX_FILE + 1))
                    elif mutation == 'root':
                        (self.policy.parent/'allowed-roots.json').write_text('{}')
                    elif mutation == 'owner': self.policy.write_text('[]')
                    elif mutation == 'reset': self.controller.boundary(old_session_id='fictional-session', session_id='replacement', reset=True)

                    return result
                with patch.object(self.controller, '_file_snapshot', side_effect=change):
                    result = await self.command('dl 1')
                self.assertFalse(self.capture.uploads)
                self.assertIn('/shelf', result)
                (self.home/'workspaces/old.md').write_text('Fictional output')
                (self.policy.parent/'allowed-roots.json').unlink(missing_ok=True)
                self.policy.write_text('["17"]')


    async def test_file_policy_denies_links_oversize_sensitive_and_unsupported(self):
        import os
        api = plugin._service()
        for path in ('credentials.zip', '.hidden.zip', '../escape.zip', 'program.exe', 'archive.tar'):
            with self.assertRaises(ValueError): api.FileRef(root='workspaces', path=path)
        await self.command('search Fictional')
        target = self.home/'workspaces/old.md'
        for mode in ('missing', 'symlink', 'hardlink', 'directory', 'oversize'):
            target.unlink(missing_ok=True)
            if mode == 'symlink': target.symlink_to(self.home/'workspaces/new.md')
            elif mode == 'hardlink': os.link(self.home/'workspaces/new.md', target)
            elif mode == 'directory': target.mkdir()
            elif mode == 'oversize': target.write_bytes(b'x' * (api.MAX_FILE + 1))
            self.assertIn('unavailable', await self.command('dl 1'))
            self.assertFalse(self.capture.uploads)
            if mode == 'directory': target.rmdir()
        target.unlink()
        target.write_text('Fictional output')
        self.assertIn('sent', await self.command('download 1'))

    async def test_duplicate_click_and_ambiguous_post_are_not_retried(self):
        token, data = await self.send_button()
        original = self.capture.do_request
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed(url, method, **kwargs):
            if url.endswith('/sendDocument'):
                started.set()
                await release.wait()
            return await original(url, method, **kwargs)
        self.capture.do_request = delayed
        first = asyncio.create_task(self.click(token, data=data))
        await started.wait()
        await self.click(token, data=data)
        self.assertIn('progress', await self.command('dl 1'))
        release.set()
        await first
        self.assertEqual(len(self.capture.uploads), 1)
        self.capture.do_request = original
        self.capture.fail.add('sendDocument')
        self.assertIn('unconfirmed', await self.command('r3'))
        self.assertEqual(sum(v == 'sendDocument' for v, d in self.capture.calls), 2)
        self.capture.fail.clear()
        self.assertIn('sent', await self.command('dl 1'))  # lock cleaned on error

    async def test_worker_read_does_not_block_loop_and_cancel_cleans_lock(self):
        import threading
        await self.command('search Fictional')
        started, release = threading.Event(), threading.Event()
        original = self.controller._file_snapshot
        def waiting(selection):
            started.set()
            release.wait(5)
            return original(selection)
        with patch.object(self.controller, '_file_snapshot', side_effect=waiting):
            task = asyncio.create_task(self.command('dl 1'))
            await asyncio.to_thread(started.wait, 2)
            self.assertTrue(started.is_set())
            await asyncio.sleep(0)  # real heartbeat while read blocked
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            release.set()
        self.assertFalse(self.capture.uploads)
        self.assertFalse(self.controller.download_busy)
    async def test_close_and_reconnect_during_ack_fence_send(self):
        token, data = await self.send_button()
        original = self.capture.do_request
        async def reconnect(url, method, request_data=None, **kwargs):
            if url.endswith('/answerCallbackQuery'):
                self.ctx.factory(self.app, object())
            return await original(url, method, request_data=request_data, **kwargs)
        self.capture.do_request = reconnect
        await self.click(token, data=data)
        self.assertFalse(self.capture.uploads)
        self.capture.do_request = original
        # Reconnect cleared the numbered snapshot as well.
        self.assertIn('Open /shelf', await self.command('dl 1'))
        await self.command('search Fictional')
        self.ctx.cleanup()
        self.assertIn('Open /shelf', await self.command('dl 1'))
        self.assertFalse(self.capture.uploads)

    async def test_profile_scope_denied_and_empty_reference_details_honest(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override
        await self.command('search Fictional')
        foreign = self.home/'profiles/foreign'
        foreign.mkdir(parents=True)
        bound = set_hermes_home_override(foreign)
        try:
            self.assertIn('Open /shelf', await self.command('dl 1'))
            self.assertFalse(self.capture.uploads)
        finally:
            reset_hermes_home_override(bound)
        (self.home/'workspaces/old.md').unlink()
        token = await self.panel()
        await self.click(token, '1')
        self.assertIn('File unavailable', self.edited()[-1]['text'])
        self.assertNotIn('Send file', str(self.edited()[-1]['reply_markup']))
        self.store.create(plugin._service().EntryInput(title='Reference', description='An unattached bundle'))
        token = await self.panel()
        await self.click(token, '1')
        self.assertIn('No file attached', self.edited()[-1]['text'])
        self.assertNotIn('Send file', str(self.edited()[-1]['reply_markup']))

    async def test_r5_payload_cap_and_partial_post_receipt(self):
        for i in range(6):
            self.store.create(plugin._service().EntryInput(title=f'Batch {i}',
                file={'root':'workspaces','path':'old.md'}))
        result = await self.command('r5')
        self.assertEqual(result, 'Shelf · 5 sent; 0 unavailable.')
        self.assertEqual(len(self.capture.uploads), 5)
        self.capture.fail.add('sendDocument')
        result = await self.command('r5')
        self.assertIn('0 sent; 0 unavailable; 4 not attempted', result)
        self.assertEqual(sum(v == 'sendDocument' for v,d in self.capture.calls), 6)

    async def test_changed_during_bounded_read_is_rejected(self):
        await self.command('search Fictional')
        api = plugin._service()
        original = api.open_file
        class ChangingStream:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(inner, bound):
                self.assertEqual(bound, 10485761)
                data = inner.stream.read(bound)
                (self.home/'workspaces/old.md').write_text('different during read')
                return data
        with patch.object(api, 'open_file', side_effect=lambda home, ref: ChangingStream(original(home, ref))):
            self.assertIn('changed', await self.command('dl 1'))
        self.assertFalse(self.capture.uploads)


# Do not rerun the entire imported base suite via inheritance/discovery.
for _name in tuple(vars(TelegramTests)):
    if _name.startswith('test_'):
        setattr(DownloadTests, _name, None)
del TelegramTests
