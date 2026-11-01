"""Real native loader + Desktop RPC/gateway/CLI dispatch, fictional stores only.

No listener, real model, Telegram send or user-client changes. Run as a script.
"""
import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch, PropertyMock

# This is a test of installed dispatch, never permission to repair/install a runtime.
os.environ['HERMES_DISABLE_LAZY_INSTALLS'] = '1'
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_telegram import prepare
from native_telegram_lifecycle import ForumRunner
# Activate the already-installed runtime before entering the fictional profile.
import hermes_bootstrap
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager, PluginContext
from hermes_state import SessionDB
from gateway.config import Platform
from gateway.session import SessionSource
from tools.registry import registry


def main():
    with tempfile.TemporaryDirectory(prefix='shelf-native-command-', dir=os.environ.get('TMPDIR')) as directory:
        home = Path(directory)/'home'
        prepare(home)
        config = home/'config.yaml'
        config.write_text(config.read_text().replace('allow_gateway_injection: true', 'allow_gateway_injection: false'))
        token = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        db = None
        try:
            with ExitStack() as guards:
                guards.enter_context(patch.dict(os.environ, {'HERMES_HOME': str(home)}))
                injection = guards.enter_context(patch.object(PluginContext, 'inject_message', side_effect=AssertionError('No injection allowed')))
                llm = guards.enter_context(patch.object(PluginContext, 'llm', new_callable=PropertyMock, side_effect=AssertionError('No LLM allowed')))
                manager.discover_and_load()
                loaded = [p for p in manager.list_plugins() if p['name']=='delivery-shelf']
                assert len(loaded)==1 and not loaded[0]['error'], loaded
                handler = manager._plugin_commands['shelf']['handler']
                search_entry = registry.get_entry('delivery_shelf_search', scope=manager.scope_key)
                assert search_entry is not None
                search = search_entry.handler
                controller = manager.get_platform_handler_factories('telegram')[0][0].__self__
                assert controller.application is None
                db = SessionDB(home/'state.db')
                for surface in ('desktop', 'tui', 'cli', 'api_server', 'telegram'):
                    db.create_session('native-'+surface, source=surface)
                    db.append_message('native-'+surface, 'assistant', 'MEDIA:'+str(home/'workspaces/first.md'))
                before = hashlib.sha256((home/'state.db').read_bytes()).hexdigest()
                from tui_gateway import server
                sessions = {surface: {'session_key': 'route-'+surface,
                    'agent': SimpleNamespace(session_id='native-'+surface), 'cwd': str(home/'workspaces'),
                    'profile_home': str(home), 'source': surface} for surface in ('desktop', 'tui')}
                guards.enter_context(patch.object(server, '_sessions', sessions))
                guards.enter_context(patch('hermes_cli.plugins.get_plugin_command_handler', side_effect=lambda name: handler if name=='shelf' else None))
                for surface in ('desktop', 'tui'):
                    result = server._methods['command.dispatch']('test', {'name': 'shelf', 'arg': 'add', 'session_id': surface})
                    print(surface, result)
                    output = result.get('result', {}).get('output', '')
                    assert 'agent handoff is unavailable or disabled' not in output, output
                    assert 'Saved to Delivery Shelf' in output or 'Already saved' in output, result
                # Real CLI fallback dispatcher, with only gateway ownership discovery
                # stubbed out: no live service contact and no interactive shell boot.
                from cli import HermesCLI
                from hermes_cli import gateway_plugin_commands
                shell: Any = SimpleNamespace(session_id='native-cli', _clarify_callback=lambda *a: (_ for _ in ()).throw(AssertionError('No clarify')))
                with patch.object(gateway_plugin_commands, 'run', return_value=None), patch('cli._cprint') as output:
                    HermesCLI._run_plugin_slash_command(shell, '/shelf', 'add')
                    assert 'Already saved' in output.call_args.args[0]
                runner = ForumRunner()
                runner.profile = controller.profile
                now = datetime.now(timezone.utc)
                for surface, native_platform in (('api_server', Platform.API_SERVER), ('telegram', Platform.TELEGRAM)):
                    source = SessionSource(platform=native_platform, chat_id='17', user_id='17', chat_type='dm', profile=controller.profile)
                    session = SimpleNamespace(session_id='native-'+surface, session_key='route-'+surface, created_at=now, updated_at=now)
                    with patch.object(controller, 'identity', wraps=controller.identity) as identity:
                        result = asyncio.run(runner._hm_run_plugin_handler(handler, cast(Any, None), source, session_entry=session, args='add'))
                        assert isinstance(result, str) and 'Already saved' in result, result
                        assert identity.call_args.args == (source, session.session_id, session.session_key, surface)
                    # Owner refusal still applies to Telegram without a PTB factory.
                    if surface=='telegram':
                        source.user_id='18'
                        result = asyncio.run(runner._hm_run_plugin_handler(handler, cast(Any, None), source, session_entry=session, args='add'))
                        assert isinstance(result, str) and 'not saved' in result and 'owner policy' in result, result
                injection.assert_not_called()
                llm.assert_not_called()
                entries = json.loads(search({}))['data']['items']
                assert len(entries)==1 and entries[0]['session_id']=='native-desktop', entries
                assert hashlib.sha256((home/'state.db').read_bytes()).hexdigest()==before
                print('PASS native Desktop/TUI RPC + CLI fallback + API/Telegram gateway dispatch; exact durable session and source owner; no PTB/inference/injection; readback')
        finally:
            if db is not None:
                db.close()
            manager.unload()
            reset_hermes_home_override(token)
        # Real out-of-process plugin host: same native RPC, serialized session
        # kwargs, no PTB Application and no weakening of isolation.
        home = Path(directory)/'isolated'
        prepare(home, 'host')
        config = home/'config.yaml'
        config.write_text(config.read_text().replace('allow_gateway_injection: true', 'allow_gateway_injection: false'))
        token = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        db = SessionDB(home/'state.db')
        db.create_session('isolated-session', source='desktop')
        db.append_message('isolated-session', 'assistant', 'MEDIA:'+str(home/'workspaces/second.md'))
        try:
            with patch.dict(os.environ, {'HERMES_HOME': str(home)}), \
                    patch.object(PluginContext, 'inject_message', side_effect=AssertionError('No host injection')) as injection, \
                    patch.object(PluginContext, 'llm', new_callable=PropertyMock, side_effect=AssertionError('No host LLM')) as llm:
                manager.discover_and_load()
                loaded = [p for p in manager.list_plugins() if p['name']=='delivery-shelf']
                assert len(loaded)==1 and not loaded[0]['error'], loaded
                assert not manager.get_platform_handler_factories('telegram')
                handler = manager._plugin_commands['shelf']['handler']
                sessions = {'isolated-ui': {'session_key': 'isolated-route', 'agent': SimpleNamespace(session_id='isolated-session'),
                    'profile_home': str(home), 'source': 'desktop', 'cwd': str(home/'workspaces')}}
                with patch.object(server, '_sessions', sessions), \
                        patch('hermes_cli.plugins.get_plugin_command_handler', side_effect=lambda name: handler if name=='shelf' else None):
                    result = server._methods['command.dispatch']('test', {'name': 'shelf', 'arg': 'add', 'session_id': 'isolated-ui'})
                    assert 'Saved to Delivery Shelf: second.md' in result.get('result', {}).get('output', ''), result
                search_entry = registry.get_entry('delivery_shelf_search', scope=manager.scope_key)
                assert search_entry is not None
                items = json.loads(search_entry.handler({}))['data']['items']
                assert len(items)==1 and items[0]['session_id']=='isolated-session' and items[0]['file']['path']=='second.md', items
                injection.assert_not_called()
                llm.assert_not_called()
                print('PASS real isolated plugin-host child + native Desktop RPC, exact session forwarding, no PTB/injection/LLM')
        finally:
            db.close()
            manager.unload()
            reset_hermes_home_override(token)


if __name__ == '__main__':
    main()
