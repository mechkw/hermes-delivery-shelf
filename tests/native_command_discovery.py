"""Real native registry/menu/help/lifecycle probe; no bot, model or production home.

Run independently or pass --companion /path/to/another/plugin to test coexistence.
HERMES_SOURCE selects the read-only official host (verified on v0.22.5).
The same self-contained probe ships in each independent repository.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('HERMES_SOURCE', Path.home() / '.hermes/hermes-agent')).resolve()
EXPECTED = {
    'delivery-shelf': ('shelf', 'Browse/add deliveries; /shelf help'),
    'conversation-bookmarks': ('bookmark', 'Save this chat; /bookmark help'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--companion', type=Path)
    args = parser.parse_args()
    roots = [ROOT] + ([args.companion.resolve()] if args.companion else [])
    # Resolve host/root before replacing all home paths; no live config, tokens or bank.
    with tempfile.TemporaryDirectory(prefix='native-command-discovery-', dir=os.environ.get('TMPDIR')) as tmp:
        home = Path(tmp) / 'profile'
        home.mkdir()
        os.environ.update(HOME=str(Path(tmp) / 'account'), HERMES_HOME=str(home),
                          HERMES_PROFILE='default', HERMES_DISABLE_TELEMETRY='1')
        os.chdir(home)
        sys.path.insert(0, str(SOURCE))
        import yaml
        from hermes_cli.plugins import get_plugin_manager, get_plugin_commands, get_plugin_command_handler
        from hermes_cli.plugin_command_dispatch import invoke_plugin_command
        from hermes_cli.commands_platforms import telegram_menu_commands, telegram_menu_max_commands
        from hermes_cli.slash_exec import execute_command, CommandContext
        from gateway.slash_commands import GatewaySlashCommandsMixin
        from gateway.platforms.base import MessageEvent
        from gateway.session import SessionSource
        from gateway.config import Platform

        ids = []
        source_hashes = {}
        for root in roots:
            manifest = yaml.safe_load((root / 'plugin.yaml').read_text())
            plugin = manifest['name']
            assert plugin in EXPECTED and plugin not in ids
            assert manifest['provides_commands'] == [EXPECTED[plugin][0]]
            ids.append(plugin)
            target = home / 'plugins' / plugin
            target.mkdir(parents=True)
            for path in root.glob('*.py'):
                shutil.copy2(path, target / path.name)
            shutil.copy2(root / 'plugin.yaml', target / 'plugin.yaml')
            shutil.copytree(root / 'dashboard', target / 'dashboard',
                            ignore=shutil.ignore_patterns('__pycache__', 'node_modules', 'dist'))
            source_hashes[plugin] = hashlib.sha256((root / '__init__.py').read_bytes()).hexdigest()
        names = [EXPECTED[p][0] for p in ids]
        config = {'plugins': {'enabled': ids, 'isolation': 'in_process'},
                  'display': {'language': 'en'}, 'skills': {'external_dirs': []}}

        def configure(menu=None, enabled=None):
            config['plugins']['enabled'] = ids if enabled is None else enabled
            config['plugins']['disabled'] = [p for p in ids if p not in config['plugins']['enabled']]
            config['platforms'] = {'telegram': {'extra': {'command_menu': menu or {}}}}
            (home / 'config.yaml').write_text(yaml.safe_dump(config))

        def menu():
            rows, hidden = telegram_menu_commands(telegram_menu_max_commands())
            assert len(rows) == len({name for name, _ in rows}), rows
            return rows, hidden

        # Actual gateway handler, including platform decoration; no GatewayRunner startup.
        runner = GatewaySlashCommandsMixin()
        event = MessageEvent(text='/help', source=SessionSource(
            platform=Platform.TELEGRAM, chat_id='17', user_id='17', chat_type='dm'))

        def native_help():
            return asyncio.run(runner._handle_help_command(event))

        configure()
        manager = get_plugin_manager()
        manager.discover_and_load()
        try:
            loaded = {p['name']: p for p in manager.list_plugins()}
            assert all(p in loaded and not loaded[p]['error'] for p in ids), loaded
            registry = get_plugin_commands()
            metadata = {}
            plugin_help = {}
            for plugin in ids:
                name, description = EXPECTED[plugin]
                entry = registry[name]
                assert entry['description'] == description and len(description) <= 40
                assert entry['argument_mode'] == 'text'
                assert entry['args_hint'].startswith('[') and '--description' in entry['args_hint']
                assert 'help' in entry['args_hint']
                metadata[name] = {key: entry[key] for key in ('description', 'args_hint', 'argument_mode')}
                handler = get_plugin_command_handler(name)
                assert callable(handler)
                reply = invoke_plugin_command(handler, 'help', platform='telegram')
                for part in (f'/{name} help', 'missing', 'current', '--description', 'groups', 'queued is not saved'):
                    assert part in reply, (name, part, reply)
                if name == 'shelf':
                    for part in ('/shelf add', '/shelf search <query>', '--file <root:path>', 'refused', 'panel Add'):
                        assert part in reply, part
                else:
                    assert 'shared' in reply and 'note' in reply
                plugin_help[name] = reply
            # Help must work without source context, metadata consent, owner file or storage writes.
            assert not list(home.rglob('*.db'))
            default_rows, default_hidden = menu()
            # Public v0.22.5's native /help AND /commands omit plugin entries entirely.
            # Lock down this observed limitation, not a fabricated plugin-rendered /help.
            help_text = native_help()
            assert '/help' in help_text and '/new' in help_text
            commands_text = execute_command('commands', CommandContext(surface='gateway', options={'page_size': 10000})).text
            for name in names:
                assert f'/{name}' not in help_text, 'Host help changed: reassess documented limitation'
                assert f'/{name}' not in commands_text, 'Host commands changed: reassess documented limitation'

            configure({'max_commands': 3})
            capped, capped_hidden = menu()
            assert len(capped) == 3 and capped_hidden > 0
            assert not set(names) & dict(capped).keys()
            priority = ['help', 'new', 'stop', *names]
            configure({'max_commands': len(priority), 'priority_mode': 'prepend', 'priority': priority})
            promoted, promoted_hidden = menu()
            assert [name for name, _ in promoted] == priority, promoted
            for name in names:
                assert dict(promoted)[name] == metadata[name]['description']  # no truncation
            # Same cap, append does not override core default priority.
            configure({'max_commands': len(priority), 'priority_mode': 'append', 'priority': names})
            appended, _ = menu()
            assert not set(names) & dict(appended).keys()
            for configured, expected in ((0, 1), (999, 100)):
                configure({'max_commands': configured})
                assert telegram_menu_max_commands() == expected
            configure({'max_commands': 100})
            complete, _ = menu()
            assert set(names) <= dict(complete).keys()

            original_handlers = {n: get_plugin_command_handler(n) for n in names}
            manager.discover_and_load(force=True)
            assert all(get_plugin_command_handler(n) is not original_handlers[n] for n in names)
            assert all(dict(menu()[0])[n] == metadata[n]['description'] for n in names)
            lifecycle = []
            for plugin in ids:
                name = EXPECTED[plugin][0]
                assert manager.unload(plugin)
                assert get_plugin_command_handler(name) is None
                assert name not in get_plugin_commands() and name not in dict(menu()[0])
                assert f'/{name}' not in native_help()
                for other in set(names) - {name}:
                    assert callable(get_plugin_command_handler(other)) and other in dict(menu()[0])
                manager.discover_and_load(force=True)
                assert all(callable(get_plugin_command_handler(n)) for n in names)
                lifecycle.append(plugin + ': unload removed entry; companion retained; force reload restored')
            configure({'max_commands': 100}, enabled=[])
            # Config alone does not unload resident commands.
            assert all(callable(get_plugin_command_handler(n)) for n in names)
            manager.discover_and_load(force=True)
            assert not set(names) & get_plugin_commands().keys()
            assert not set(names) & dict(menu()[0]).keys()
            assert not list(home.rglob('*.db'))
            print(json.dumps({
                'result': 'PASS', 'plugins': ids,
                'host_commit': subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
                'init_sha256': source_hashes, 'metadata': metadata,
                'default_menu_count': len(default_rows), 'default_hidden': default_hidden,
                'default_plugin_entries': [row for row in default_rows if row[0] in names],
                'capped_menu': capped, 'capped_hidden': capped_hidden,
                'promoted_menu': promoted, 'promoted_hidden': promoted_hidden,
                'append_menu': appended, 'native_help': help_text,
                'native_commands_plugin_entries': [], 'plugin_help': plugin_help,
                'lifecycle': lifecycle, 'disable_requires_reload': True,
                'no_catalog_writes': True,
                'limitation': 'v0.22.5 native gateway /help and /commands omit plugin commands, including args_hint',
            }, indent=2))
        finally:
            manager.unload()


if __name__ == '__main__':
    main()
