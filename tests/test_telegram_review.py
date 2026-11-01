"""P2 review regressions: real PTB/SQLite, fictional homes, no network/model."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

import test_telegram as fixture
from gateway.session import SessionSource, SessionStore, build_session_key
from gateway.config import GatewayConfig, Platform


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.t = fixture.TelegramTests(methodName='test_add_queue_register_search_readback_and_replay')
        await self.t.asyncSetUp()

    async def asyncTearDown(self):
        await self.t.asyncTearDown()

    async def test_completed_add_then_explicit_metadata_request(self):
        t = self.t
        await t.assisted_request()
        first = json.loads(t.ctx.queued[-1][0].split('\n', 1)[1])['supplied']['request_id']
        with t.session():
            saved = json.loads(await asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], {
                'title': 'First Add', 'file': {'root':'workspaces', 'path':'new.md'},
                'session_id':'fictional-session', 'request_id':first}))
            self.assertTrue(saved['ok'], saved)
            self.assertEqual(t.store.get(saved['data']['id']), saved['data'])
            answer = await asyncio.to_thread(t.ctx.commands['shelf'], 'add SecondCase #Keep-Tag --file workspaces:third.md',
                source=t.source, session_id='fictional-session', session_key='telegram:17:9', platform='telegram')
            self.assertIsNone(answer)
            supplied = json.loads(t.ctx.queued[-1][0].split('\n', 1)[1])['supplied']
            self.assertNotEqual(supplied['request_id'], first)
            args = {**supplied, 'description':'Fresh completion'}
            for change in ({'request_id':None}, {'file':{'root':'workspaces','path':'old.md'}},
                           {'title':'Wrong'}, {'session_id':'another'}):
                invalid = {**args, **change}
                if invalid['request_id'] is None: invalid.pop('request_id')
                result = json.loads(await asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], invalid))
                self.assertFalse(result['ok'], result)
            saved = json.loads(await asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], args))
            self.assertTrue(saved['ok'], saved)
            self.assertEqual(t.store.get(saved['data']['id']), saved['data'])
            self.assertEqual(saved['data']['title'], 'SecondCase')
            self.assertEqual(saved['data']['tags'], ['Keep-Tag'])
            self.assertFalse(json.loads(await asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], args))['ok'])
        t.ctx.hooks['on_session_reset'](old_session_id='fictional-session', session_id='fresh')
        with t.session(session_id='fresh'):
            self.assertFalse(json.loads(await asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], args))['ok'])
        self.assertEqual(t.store.search(q='SecondCase')['total'], 1)

    async def test_shared_topic_refuses_before_queue_but_explicit_save_works(self):
        t = self.t
        origin = SessionSource(platform=Platform.TELEGRAM, user_id='18', chat_id='-100', chat_type='group', thread_id='9')
        caller = SessionSource(platform=Platform.TELEGRAM, user_id='17', chat_id='-100', chat_type='group', thread_id='9', message_id='22')
        self.assertEqual(build_session_key(origin), build_session_key(caller))
        sessions = await asyncio.to_thread(SessionStore, t.home/'sessions', GatewayConfig())
        entry = await asyncio.to_thread(sessions.get_or_create_session, origin)
        same = await asyncio.to_thread(sessions.get_or_create_session, caller)
        self.assertEqual(entry.session_id, same.session_id)
        assert entry.origin is not None
        self.assertEqual(entry.origin.user_id, '18')
        identity = t.controller.identity(caller, entry.session_id, entry.session_key, 'telegram')
        self.assertIsNone(await t.controller.send(identity))
        self.assertIn('Add', [row[0]['text'] for row in t.sent()[-1]['reply_markup']['inline_keyboard']])
        await t.click(next(reversed(t.controller.panels)), '1', chat=-100)
        self.assertIn('Shelf · Details', t.edited()[-1]['text'])
        for command in ('add Second --file workspaces:third.md',):
            answer = await asyncio.to_thread(t.ctx.commands['shelf'], command, source=caller,
                session_id=entry.session_id, session_key=entry.session_key, platform='telegram')
            self.assertIn('Nothing queued', answer)
        self.assertEqual(t.ctx.queued, [])
        self.assertEqual(t.controller.requests, {})
        result = await asyncio.to_thread(t.ctx.commands['shelf'],
            'add GroupCase #Keep-Tag --file workspaces:third.md --description "Explicit group save"',
            source=caller, session_id=entry.session_id, session_key=entry.session_key, platform='telegram')
        self.assertIn('Saved', result)
        self.assertEqual(t.store.search(q='GroupCase')['total'], 1)
        with t.session(chat_id='-100', session_id=entry.session_id, session_key=entry.session_key):
            offered = json.loads(await asyncio.to_thread(t.ctx.tools['delivery_shelf_offer_update'],
                {'id':t.entry['id'], 'file':{'root':'workspaces','path':'new.md'}}))
        self.assertEqual(offered['status'], 'offered')
        await t.click(next(reversed(t.controller.panels)), chat=-100)
        updated = t.store.get(t.entry['id'])
        self.assertEqual(updated['file']['path'], 'new.md')
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['tags'], t.entry['tags'])

    @asynccontextmanager
    async def sqlite_wait(self):
        """Observe the actual BEGIN IMMEDIATE attempt; don't guess worker scheduling."""
        t = self.t
        lock = sqlite3.connect(t.store.path)
        lock.execute('BEGIN IMMEDIATE')
        entered = threading.Event()
        Store = fixture.plugin._service().Store
        original = Store.connect
        @contextmanager
        def connect(store):
            with original(store) as conn:
                conn.set_trace_callback(lambda sql: entered.set() if sql == 'BEGIN IMMEDIATE' else None)
                yield conn
        try:
            with patch.object(Store, 'connect', connect):
                yield entered
        finally:
            lock.rollback()
            lock.close()

    async def waiting(self, event):
        self.assertTrue(await asyncio.to_thread(event.wait, 2), 'worker never attempted SQLite write')

    async def test_sqlite_contention_heartbeat_and_double_click(self):
        t = self.t
        await t.offer()
        token = next(reversed(t.controller.panels))
        async with self.sqlite_wait() as entered:
            action = asyncio.create_task(t.click(token))
            await self.waiting(entered)
            start = time.monotonic()
            await asyncio.sleep(.05)
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, .25)
            self.assertFalse(action.done())
            await asyncio.wait_for(t.click(token), .5)
            self.assertTrue(t.controller.panels[token].busy)
        await action
        self.assertEqual(t.store.get(t.entry['id'])['revision'], 2)
        print(f'PASS SQLite contention: 50 ms heartbeat {elapsed:.3f}s; concurrent second click refused; single CAS')

    async def test_waiting_update_reset_unload_revocation_and_expiry(self):
        # Each subcase has its own fixture, so unload/fencing cannot mask later cases.
        for boundary in ('reset','unload','owners','roots','expiry','reconnect'):
            if boundary != 'reset':
                await self.asyncTearDown()
                await self.asyncSetUp()
            t = self.t
            with self.subTest(boundary=boundary):
                await t.offer()
                token = next(reversed(t.controller.panels))
                async with self.sqlite_wait() as entered:
                    action = asyncio.create_task(t.click(token))
                    await self.waiting(entered)
                    if boundary == 'reset':
                        t.ctx.hooks['on_session_reset'](old_session_id='fictional-session', session_id='fresh')
                    elif boundary == 'unload': t.ctx.cleanup()
                    elif boundary == 'owners': t.policy.write_text('[]')
                    elif boundary == 'roots': (t.policy.parent/'allowed-roots.json').write_text('{}')
                    elif boundary == 'expiry': t.controller.panels[token].expires = 0
                    else: t.ctx.factory(t.app, object())
                    await asyncio.sleep(.05)
                    self.assertFalse(action.done())
                await action
                self.assertEqual(t.store.get(t.entry['id']), t.entry)
                self.assertFalse(any('Shelf · Updated' in row['text'] for row in t.edited()))

    async def test_waiting_register_does_not_hold_controller_lock(self):
        t = self.t
        await t.assisted_request()
        request = json.loads(t.ctx.queued[-1][0].split('\n', 1)[1])['supplied']['request_id']
        another = await t.panel()
        with t.session():
            async with self.sqlite_wait() as entered:
                action = asyncio.create_task(asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], {
                    'title':'Waiting', 'session_id':'fictional-session', 'request_id':request,
                    'file':{'root':'workspaces','path':'new.md'}}))
                await self.waiting(entered)
                await asyncio.wait_for(t.click(another), .5)
                t.ctx.hooks['on_session_reset'](old_session_id='fictional-session', session_id='fresh')
                t.ctx.cleanup()
                await asyncio.sleep(.05)
                self.assertFalse(action.done())
            self.assertFalse(json.loads(await action)['ok'])
        self.assertEqual(t.store.search()['total'], 1)

    async def test_policy_catalog_and_lock_waits_are_off_loop(self):
        t = self.t
        # Policy and catalog calls must execute off the PTB thread, including paging.
        main = threading.get_ident()
        owners, search = t.controller.owners, fixture.plugin._service().Store.search
        def checked_owners():
            self.assertNotEqual(threading.get_ident(), main)
            return owners()
        def checked_search(store, *args, **kwargs):
            self.assertNotEqual(threading.get_ident(), main)
            return search(store, *args, **kwargs)
        with patch.object(t.controller, 'owners', checked_owners), patch.object(fixture.plugin._service().Store, 'search', checked_search):
            token = await t.panel()
            await t.click(token, '2')  # Browse more
        held, release = threading.Event(), threading.Event()
        def locker():
            with t.controller.lock:
                held.set()
                release.wait(2)
        worker = threading.Thread(target=locker)
        worker.start()
        await self.waiting(held)
        try:
            action = asyncio.create_task(t.click(token))
            start = time.monotonic()
            await asyncio.sleep(.05)
            self.assertLess(time.monotonic() - start, .25)
            self.assertFalse(action.done())
        finally:
            release.set()
            await asyncio.to_thread(worker.join)
        await action


    async def test_cancelled_waiting_callback_cannot_commit(self):
        t = self.t
        await t.offer()
        token = next(reversed(t.controller.panels))
        finished = threading.Event()
        perform = t.controller._perform
        def observed(*args):
            try: return perform(*args)
            finally: finished.set()
        with patch.object(t.controller, '_perform', observed):
            async with self.sqlite_wait() as entered:
                action = asyncio.create_task(t.click(token))
                await self.waiting(entered)
                action.cancel()
                with self.assertRaises(asyncio.CancelledError): await action
                self.assertNotIn(token, t.controller.panels)
            await self.waiting(finished)
        self.assertEqual(t.store.get(t.entry['id']), t.entry)

    async def test_concurrent_register_claim_is_one_shot(self):
        t = self.t
        await t.assisted_request()
        request = json.loads(t.ctx.queued[-1][0].split('\n', 1)[1])['supplied']['request_id']
        args = {'title':'Concurrent', 'session_id':'fictional-session', 'request_id':request,
                'file':{'root':'workspaces','path':'new.md'}}
        with t.session():
            results = await asyncio.gather(*(asyncio.to_thread(t.ctx.tools['delivery_shelf_register'], args) for _ in range(2)))
        self.assertEqual(sum(json.loads(result)['ok'] for result in results), 1)
        self.assertEqual(t.store.search(q='Concurrent')['total'], 1)


if __name__ == '__main__': unittest.main()
