"""Quick-Add isolation admission, real native host, and manual Save regression."""
import asyncio
from contextlib import ExitStack, contextmanager
import importlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, PropertyMock, MagicMock, Mock

from native_telegram import prepare
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager, PluginContext
from hermes_cli.plugin_command_dispatch import invoke_plugin_command
from hermes_state import SessionDB
from tools.registry import registry


class IsolatedQuickAddTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shelf-isolated-add-', dir=os.environ.get('TMPDIR'))
        self.home = Path(self.temp.name)/'home'
        self.bound = set_hermes_home_override(self.home)
        self.manager = None
        self.db = None

    async def asyncTearDown(self):
        if self.manager:
            await asyncio.to_thread(self.manager.unload)
        if self.db:
            self.db.close()
        reset_hermes_home_override(self.bound)
        self.temp.cleanup()

    async def load(self, isolation):
        prepare(self.home, isolation)
        self.db = SessionDB(self.home/'state.db')
        self.db.create_session('fictional-current', source='desktop')
        self.db.append_message('fictional-current', 'user', 'Create fictional notes.')
        self.db.append_message('fictional-current', 'assistant',
            'MEDIA:'+str(self.home/'workspaces/first.md'))
        self.manager = PluginManager(str(self.home))
        await asyncio.to_thread(self.manager.discover_and_load)
        info = [p for p in self.manager.list_plugins() if p['name']=='delivery-shelf']
        self.assertEqual(len(info), 1)
        self.assertFalse(info[0]['error'], info)
        self.handler = self.manager._plugin_commands['shelf']['handler']

    async def command(self, raw='add', platform='desktop'):
        result = invoke_plugin_command(self.handler, raw, platform=platform,
            session_id='fictional-current', session_key='fictional-route')
        return await result if inspect.isawaitable(result) else result

    def entries(self):
        assert self.manager is not None
        tool = registry.get_entry('delivery_shelf_search', scope=self.manager.scope_key)
        assert tool is not None
        result = json.loads(tool.handler({}))
        self.assertTrue(result['ok'], result)
        return result['data']['items']

    def assert_rejected(self, reply):
        self.assertIn('not saved', reply)
        self.assertIn('isolated plugin host', reply)
        self.assertIn('cancellation', reply)
        self.assertIn('Saved → Delivery Shelf → Add', reply)
        self.assertIn('then Save', reply)

    async def test_preflight_rejects_before_source_catalog_locks_or_inference(self):
        await self.load('in_process')
        assert self.manager is not None
        controller = self.manager.get_platform_handler_factories('telegram')[0][0].__self__
        quick = importlib.import_module(controller.__class__.__module__.rsplit('.', 1)[0]+'.agent_quick_add')
        identity = dict(platform='desktop', profile=controller.profile,
            session_id='fictional-current', session_key='fictional-route')
        # Run the real worker entry. Any work past preflight is a test failure,
        # including fully supplied metadata and the generate_metadata=False case.
        for generate in (True, False):
            controller.api.Store(self.home).save_settings({'generate_metadata': generate})
            for raw in ('', 'Exact #Keep --description "Literal."'):
                with self.subTest(generate=generate, raw=raw), ExitStack() as guards:
                    guards.enter_context(patch.dict(os.environ, HERMES_PLUGIN_HOST_PROCESS='1'))
                    for target, name in ((quick, 'recent'), (quick, 'candidates'),
                            (quick, 'generation_request'), (controller.api, 'Store'),
                            (controller.api, 'file_stamp'), (controller.api, 'generate_draft')):
                        guards.enter_context(patch.object(target, name,
                            side_effect=AssertionError('Preflight must precede '+name)))
                    guards.enter_context(patch.object(controller, 'lock',
                        new=MagicMock(__enter__=Mock(
                            side_effect=AssertionError('Preflight must precede lifecycle lock')))))
                    reply = controller._prepare_text_add(identity, raw, controller.epoch, threading.Event())
                    self.assert_rejected(reply)
        self.assertEqual(self.entries(), [])

    async def test_real_isolated_dispatch_rejects_and_manual_save_still_works(self):
        with patch.dict(os.environ, HERMES_HOME=str(self.home)), \
                patch.object(PluginContext, 'llm', new_callable=PropertyMock,
                    side_effect=AssertionError('No automatic inference')) as llm:
            await self.load('host')
            assert self.manager is not None
            self.assertTrue(hasattr(self.handler, '__hermes_plugin_host_ref__'))
            self.assertEqual(self.manager.get_platform_handler_factories('telegram'), [])
            from tui_gateway import server
            sessions = {'fictional-ui': {'session_key':'fictional-route',
                'agent':SimpleNamespace(session_id='fictional-current'),
                'profile_home':str(self.home), 'source':'desktop',
                'cwd':str(self.home/'workspaces')}}
            with patch.object(server, '_sessions', sessions), \
                    patch('hermes_cli.plugins.get_plugin_command_handler',
                        return_value=self.handler):
                rpc = await asyncio.to_thread(server._methods['command.dispatch'], 'fixture',
                    {'name':'shelf', 'arg':'add', 'session_id':'fictional-ui'})
                self.assert_rejected(rpc['result']['output'])
            for platform in ('desktop', 'tui', 'cli', 'api_server'):
                for raw in ('add', 'add Exact #Keep --description "Literal."'):
                    with self.subTest(platform=platform, raw=raw):
                        self.assert_rejected(await self.command(raw, platform))
            self.assertEqual(self.entries(), [])
            self.assertFalse((self.home/'plugin-data/delivery-shelf/add.lock').exists())
            # Use the real isolated host's ASGI forwarding, not a model of Save.
            host = self.manager._plugin_host()
            def request(method, path, payload=None):
                reply = host.asgi_request('delivery-shelf',
                    str(self.home/'plugins/delivery-shelf/dashboard'), 'plugin_api.py',
                    method, path, '', [('content-type', 'application/json')],
                    json.dumps(payload).encode() if payload else b'', authenticated=True)
                return reply['status'], json.loads(reply['body'])
            payload = dict(title='Manual fictional save', description='Exact manual details.',
                tags=['Keep'], session_id='fictional-current',
                file={'root':'workspaces', 'path':'first.md'})
            status, manual = await asyncio.to_thread(request, 'POST', '/entries', payload)
            self.assertEqual(status, 201, manual)
            self.assertEqual(self.entries(), [manual])
            for key, value in payload.items():
                self.assertEqual(manual[key], value)
            llm.assert_not_called()

    async def test_in_process_supplied_metadata_and_same_path_duplicate_unchanged(self):
        with patch.object(PluginContext, 'llm', new_callable=PropertyMock,
                side_effect=AssertionError('Supplied fields and duplicates need no inference')):
            await self.load('in_process')
            self.assertEqual(await self.command('add Exact #Keep --description "Literal."'),
                'Saved to Delivery Shelf: Exact')
            saved = self.entries()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]['description'], 'Literal.')
            self.assertEqual(saved[0]['tags'], ['Keep'])
            (self.home/'workspaces/first.md').write_text('Changed fictional bytes at same path')
            self.assertEqual(await self.command(), 'Already saved to Delivery Shelf: Exact')
            self.assertEqual(self.entries(), saved)

    async def test_in_process_cancel_while_waiting_for_sqlite_never_saves(self):
        await self.load('in_process')
        assert self.manager is not None
        controller = self.manager.get_platform_handler_factories('telegram')[0][0].__self__
        Store = controller.api.Store
        register, connect = Store.register_file_once, Store.connect
        prepare_worker = controller._prepare_text_add
        waiting, finished = threading.Event(), threading.Event()
        blockers = []
        def contended(store, entry, **kwargs):
            # Take the real SQLite reservation after discovery/initialization.
            blocker = sqlite3.connect(store.path, check_same_thread=False)
            blocker.execute('BEGIN IMMEDIATE')
            blockers.append(blocker)
            return register(store, entry, **kwargs)
        @contextmanager
        def traced(store):
            with connect(store) as conn:
                conn.set_trace_callback(lambda sql: waiting.set() if sql=='BEGIN IMMEDIATE' else None)
                yield conn
        def observed(*args):
            try:
                return prepare_worker(*args)
            finally:
                finished.set()
        with patch.object(Store, 'register_file_once', contended), \
                patch.object(Store, 'connect', traced), \
                patch.object(controller, '_prepare_text_add', observed):
            task = asyncio.create_task(self.command('add Exact #Keep --description "Literal."'))
            try:
                self.assertTrue(await asyncio.to_thread(waiting.wait, 5))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                for blocker in blockers:
                    blocker.rollback()
                self.assertTrue(await asyncio.to_thread(finished.wait, 5))
                self.assertEqual(self.entries(), [])
            finally:
                for blocker in blockers:
                    blocker.close()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_native_isolated_caller_cancel_does_not_cancel_child(self):
        # A tiny fictional plugin measures the native lifecycle boundary directly.
        # No Shelf safety guard is bypassed and no live catalog/provider is used.
        package = self.home/'plugins/lifecycle-probe'
        package.mkdir(parents=True)
        (package/'plugin.yaml').write_text('name: lifecycle-probe\nversion: 0.0.1\ndescription: Fictional lifecycle probe\n')
        (package/'__init__.py').write_text('''import asyncio
from pathlib import Path
from hermes_constants import get_hermes_home

def register(ctx):
    async def probe(args="", **kwargs):
        home = Path(get_hermes_home())
        (home/"entered").write_text("entered")
        while not (home/"release").exists():
            await asyncio.sleep(.01)
        (home/"completed").write_text("completed after caller cancellation")
        return "completed"
    ctx.register_command("lifecycleprobe", probe, description="Fictional lifecycle probe")
''')
        (self.home/'config.yaml').write_text('plugins:\n  enabled: [lifecycle-probe]\n  isolation: host\n')
        self.manager = PluginManager(str(self.home))
        with patch.dict(os.environ, HERMES_HOME=str(self.home)):
            await asyncio.to_thread(self.manager.discover_and_load)
            info = [p for p in self.manager.list_plugins() if p['name']=='lifecycle-probe']
            self.assertEqual(len(info), 1)
            self.assertFalse(info[0]['error'], info)
            handler = self.manager._plugin_commands['lifecycleprobe']['handler']
            self.assertTrue(hasattr(handler, '__hermes_plugin_host_ref__'))
            task = asyncio.create_task(invoke_plugin_command(handler, '', platform='desktop',
                session_id='fictional-probe', session_key='fictional-route'))
            try:
                async def wait_for(path):
                    while not path.exists():
                        await asyncio.sleep(.01)
                await asyncio.wait_for(wait_for(self.home/'entered'), 5)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                (self.home/'release').touch()
                await asyncio.wait_for(wait_for(self.home/'completed'), 5)
                self.assertEqual((self.home/'completed').read_text(),
                    'completed after caller cancellation')
            finally:
                (self.home/'release').touch()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
