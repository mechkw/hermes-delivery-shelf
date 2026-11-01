"""Cross-surface deterministic Add; source/policy/lifecycle fail-closed tests."""
import asyncio
from contextlib import contextmanager, closing
import hashlib
import importlib
import inspect
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from test_commands import Context, plugin, invoke_plugin_command
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_state import SessionDB


class NativeContext(Context):
    def register_platform_handler(self, platform, factory):
        self.controller = factory.__self__

    def inject_message(self, *args, **kwargs):
        raise AssertionError('Ordinary Add must not inject')

    @property
    def llm(self):
        raise AssertionError('Ordinary Add must not access a model')


class MultisurfaceAddTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shelf-text-add-', dir=os.environ.get('TMPDIR'))
        self.home = Path(self.tmp.name)/'home'
        (self.home/'workspaces').mkdir(parents=True)
        for name in ('one.md', 'two.md'):
            (self.home/'workspaces'/name).write_text('Fictional deliverable')
        self.token = set_hermes_home_override(self.home)
        self.ctx = NativeContext()
        plugin.register(self.ctx)
        self.controller = self.ctx.controller
        self.api = plugin._service()
        self.store = self.api.Store(self.home)
        self.source = importlib.import_module(plugin.__name__+'.recent_artifacts')
        self.db = SessionDB(self.home/'state.db')
        self.db.create_session('current-session', source='desktop')

    async def asyncTearDown(self):
        self.controller.close()
        self.db.close()
        reset_hermes_home_override(self.token)
        self.tmp.cleanup()

    def deliver(self, *names):
        return self.db.append_message('current-session', 'assistant', '\n'.join('MEDIA:'+str(self.home/'workspaces'/name) for name in names))

    async def command(self, text='add', **kwargs):
        context = dict(platform='desktop', source=None, session_id='current-session', session_key='route-not-session') | kwargs
        result = invoke_plugin_command(self.ctx.commands['shelf'], text, **context)
        return await result if inspect.isawaitable(result) else result

    async def test_supported_surfaces_direct_save_dedupe_metadata_readback_no_ptb(self):
        self.deliver('one.md')
        before = hashlib.sha256((self.home/'state.db').read_bytes()).hexdigest()
        for platform in ('desktop', 'tui', 'cli', 'api_server', 'local'):
            with self.subTest(platform=platform):
                text = await self.command('add Exact #Keep --description "Literal."', platform=platform)
                self.assertIn('saved to delivery shelf', text.lower())
        entries = self.store.search()['items']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['session_id'], 'current-session')
        self.assertEqual(entries[0]['title'], 'Exact')
        self.assertEqual(entries[0]['tags'], ['Keep'])
        self.assertEqual(entries[0]['description'], 'Literal.')
        self.assertEqual(entries[0]['revision'], 1)
        self.assertIn('Already saved', await self.command('add Ignored #Ignored'))
        self.assertEqual(self.store.search()['items'], entries)
        self.assertEqual(hashlib.sha256((self.home/'state.db').read_bytes()).hexdigest(), before)
        self.assertIsNone(self.controller.application)

    async def test_bare_browses_multiple_requires_saved_picker(self):
        self.deliver('one.md', 'two.md')
        self.assertIn('matching deliveries', await self.command(''))
        text = await self.command()
        self.assertIn('Nothing saved', text)
        self.assertIn('Saved → Delivery Shelf', text)
        self.assertNotIn('--file', text)
        self.assertEqual(self.store.search()['total'], 0)

    async def test_missing_context_unknown_surface_and_foreign_profile_no_queries(self):
        for kwargs in ({'session_id': ''}, {'session_id': '../bad'}, {'session_key': ''}, {'platform': 'unknown'}):
            with self.subTest(kwargs=kwargs), patch.object(self.source, 'recent', side_effect=AssertionError('No source query')):
                self.assertIn('not saved', await self.command(**kwargs))
        token = set_hermes_home_override(self.home/'foreign')
        try:
            with patch.object(self.source, 'recent', side_effect=AssertionError('No foreign source query')), \
                    patch.object(self.api, 'Store', side_effect=AssertionError('No foreign catalog query')):
                self.assertIn('profile changed', await self.command())
        finally:
            reset_hermes_home_override(token)

    async def test_missing_foreign_session_and_disallowed_file_fail_without_handoff(self):
        self.assertIn('No recent file', await self.command())
        self.db.create_session('foreign-session', source='desktop')
        with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
            conn.execute("UPDATE sessions SET profile_name='foreign' WHERE id='foreign-session'")
        self.assertIn('unavailable', await self.command(session_id='foreign-session'))
        self.deliver('../outside.md')
        self.assertIn('not saved', await self.command())
        self.assertEqual(self.store.search()['total'], 0)

    async def test_source_edit_after_discovery_never_commits(self):
        row = self.deliver('one.md')
        original = self.api.Store.register_file_once
        def changed(store, entry, **kwargs):
            with closing(sqlite3.connect(self.home/'state.db')) as conn, conn:
                conn.execute('UPDATE messages SET content=? WHERE id=?', ('MEDIA:'+str(self.home/'workspaces/two.md'), row))
            return original(store, entry, **kwargs)
        with patch.object(self.api.Store, 'register_file_once', changed):
            self.assertIn('delivery changed', await self.command())
        self.assertEqual(self.store.search()['total'], 0)

    async def test_post_commit_failure_is_ambiguous_not_false_rollback(self):
        self.deliver('one.md')
        original = self.api.Store.register_file_once
        def completed(store, entry, **kwargs):
            result = original(store, entry, **kwargs)
            self.controller.close()
            return result
        with patch.object(self.api.Store, 'register_file_once', completed):
            text = await self.command()
        self.assertIn('Unable to confirm', text)
        self.assertNotIn('not saved', text)
        self.assertEqual(self.store.search()['total'], 1)

    async def test_source_profile_and_surface_mismatch_refused_before_reads(self):
        from types import SimpleNamespace
        for source in (SimpleNamespace(profile='foreign', platform=SimpleNamespace(value='api_server')),
                       SimpleNamespace(profile=self.controller.profile, platform=SimpleNamespace(value='cli'))):
            with patch.object(self.source, 'recent', side_effect=AssertionError('No source query')):
                self.assertIn('not saved', await self.command(platform='api_server', source=source))

    async def test_concurrent_commands_save_once(self):
        self.deliver('one.md')
        replies = await asyncio.gather(self.command(), self.command())
        self.assertEqual(sum('Already saved' in r for r in replies), 1)
        self.assertEqual(self.store.search()['total'], 1)

    async def test_write_wait_cancellation_reset_close_profile_and_policy_rechecked(self):
        self.deliver('one.md')
        for change in ('cancel', 'reset', 'close', 'profile', 'policy'):
            with self.subTest(change=change):
                # Each iteration gets a fresh plugin lifecycle, same untouched catalog.
                self.controller.close()
                plugin.register(self.ctx)
                self.controller = self.ctx.controller
                entered, finished = threading.Event(), threading.Event()
                current_home = [self.home]
                original = self.api.Store.connect
                prepare = self.controller._prepare_text_add
                @contextmanager
                def traced(store):
                    with original(store) as conn:
                        conn.set_trace_callback(lambda sql: entered.set() if sql=='BEGIN IMMEDIATE' else None)
                        yield conn
                def observed(*args):
                    try:
                        return prepare(*args)
                    finally:
                        finished.set()
                lock = sqlite3.connect(self.store.path)
                lock.execute('BEGIN IMMEDIATE')
                try:
                    with patch.object(self.api.Store, 'connect', traced), \
                            patch.object(self.controller, '_prepare_text_add', observed), \
                            patch.object(self.api, 'bound_home', side_effect=lambda: current_home[0]), \
                            patch.object(self.source, 'recent', wraps=self.source.recent) as recent:
                        task = asyncio.create_task(self.command())
                        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                        count = recent.call_count
                        if change=='cancel':
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                        elif change=='reset':
                            self.controller.boundary(old_session_id='current-session', session_id='new', reset=True)
                        elif change=='close':
                            self.controller.close()
                        elif change=='profile':
                            current_home[0] = self.home/'foreign'
                        else:
                            (self.home/'workspaces/one.md').unlink()
                        lock.rollback()
                        if change!='cancel':
                            self.assertNotIn('Saved to Delivery Shelf:', await asyncio.wait_for(task, 3))
                        self.assertTrue(await asyncio.to_thread(finished.wait, 2))
                        self.assertEqual(recent.call_count, count, 'No source query after invalidation')
                    self.assertEqual(self.store.search()['total'], 0)
                finally:
                    lock.close()
                    (self.home/'workspaces/one.md').write_text('Fictional deliverable')
