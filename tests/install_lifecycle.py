"""Native Git installer and Desktop reconciliation, exclusively in disposable homes.

Run with HERMES_SOURCE pointing to a disposable official Hermes checkout.
The native installer may bootstrap PM into that checkout; never use a live install.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    scratch = Path(os.environ['TMPDIR']).resolve()
    if not source.is_relative_to(scratch):
        raise SystemExit('HERMES_SOURCE must be a disposable checkout beneath TMPDIR')
    with tempfile.TemporaryDirectory(prefix='shelf-install-', dir=scratch) as tmp:
        base = Path(tmp)
        home = base / 'account'
        bank = home / '.hermes'
        bank.mkdir(parents=True)
        # Do not inherit credentials, provider settings, profile context or PM roots.
        env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
        env.update(HOME=str(home), HERMES_HOME=str(bank), HERMES_PROFILE='default',
                   TMPDIR=str(base), XDG_CACHE_HOME=str(base/'cache'),
                   HERMES_DISABLE_TELEMETRY='1', PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPATH=str(source), GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL=os.devnull)
        fixture = base/'fixture'
        fixture.mkdir()
        for source_file in (ROOT/'plugin.yaml', ROOT/'VERSION', *ROOT.glob('*.py')):
            shutil.copy2(source_file, fixture/source_file.name)
        for name in ('dashboard', 'desktop'):
            shutil.copytree(ROOT/name, fixture/name, ignore=shutil.ignore_patterns('__pycache__'))
        def run(args, cwd=fixture):
            return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240).stdout
        def git(*args):
            return run(['git', *args]).strip()
        git('init', '-q'); git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'user.name', 'Fictional CI'); git('add', '.')
        git('commit', '-qm', 'fictional install fixture')
        def native(code):
            try:
                print(run([sys.executable, '-c', code], cwd=source))
            except subprocess.CalledProcessError as exc:
                print(exc.stdout)
                raise
        target = bank/'plugins/delivery-shelf'
        # A custom Git source with known caution findings needs explicit consent.
        # Prove default refusal before accepting the reviewed fictional fixture.
        try:
            native('from hermes_cli.plugins_cmd_install import cmd_install; '
                   f'cmd_install({fixture.as_uri()!r}, enable=False, no_deps=True)')
        except subprocess.CalledProcessError as exc:
            assert 'caution' in exc.stdout and 'BLOCKED' in exc.stdout, exc.stdout
        else:
            raise AssertionError('Unconfirmed caution install must be refused')
        assert not target.exists()
        native('from hermes_cli.plugins_cmd_install import cmd_install; '
               f'cmd_install({fixture.as_uri()!r}, force=True, enable=False, no_deps=True)')
        for name in ('__init__.py', 'telegram_shelf.py', 'recent_artifacts.py', 'dashboard/plugin_api.py', 'dashboard/dist/index.js', 'desktop/plugin.js'):
            assert (target/name).read_bytes() == (fixture/name).read_bytes(), name
        # Exercise the actual Electron filesystem implementation without Electron/IPC.
        module = base/'desktop-root.mjs'
        run([str(ROOT/'node_modules/esbuild/bin/esbuild'),
             str(source/'apps/desktop/electron/desktop-plugins-root.ts'), '--bundle',
             '--platform=node', '--format=esm', '--outfile='+str(module)], cwd=ROOT)
        def reconcile():
            run(['node', '--input-type=module', '-e',
                 f'import {{reconcileUnifiedDesktopHalves as sync}} from {json.dumps(module.as_uri())}; '
                 f'await sync({json.dumps(str(bank))}, {json.dumps(str(bank/"desktop-plugins"))});'], cwd=ROOT)
        reconcile()
        desktop = bank/'desktop-plugins/delivery-shelf'
        assert (desktop/'plugin.js').read_bytes() == (target/'desktop/plugin.js').read_bytes()
        assert json.loads((desktop/'.hermes-package.json').read_text())['package'] == 'delivery-shelf'
        native('from hermes_cli.plugins_cmd import cmd_enable; cmd_enable("delivery-shelf")')
        def selection(enabled):
            import yaml
            config = yaml.safe_load((bank/'config.yaml').read_text())['plugins']
            assert ('delivery-shelf' in config.get('enabled', [])) == enabled, config
        selection(True)
        # Use the actual store rather than a hand-written sentinel database.
        native('import importlib.util; from pathlib import Path; '
               f'p=Path({str(target/"dashboard/plugin_api.py")!r}); '
               's=importlib.util.spec_from_file_location("shelf_fixture",p); '
               'm=importlib.util.module_from_spec(s); import sys; sys.modules[s.name]=m; s.loader.exec_module(m); '
               f'm.Store(Path({str(bank)!r})).create(m.EntryInput(title="Fictional retained delivery"))')
        databases = list(bank.rglob('shelf.sqlite3'))
        assert len(databases) == 1
        before = databases[0].read_bytes()
        native('from hermes_cli.plugins_cmd import cmd_disable; cmd_disable("delivery-shelf")')
        selection(False)
        assert databases[0].read_bytes() == before
        reconcile()
        # Disabled is not uninstalled: the app-wide copy remains on disk.
        assert (desktop/'plugin.js').is_file()
        with (fixture/'desktop/plugin.js').open('a') as stream:
            stream.write('\n// Fictional lifecycle revision two.\n')
        git('add', '.'); git('commit', '-qm', 'fictional update fixture')
        def installed_bytes():
            return {p.relative_to(target).as_posix(): p.read_bytes()
                    for p in target.rglob('*')
                    if p.is_file() and '.git' not in p.relative_to(target).parts}
        installed_before = installed_bytes()
        native('from hermes_cli.plugins_transaction import update_plugin; '
               'from hermes_cli.plugins_cmd import PluginScanBlocked; from pathlib import Path;\n'
               'try:\n'
               f' update_plugin(Path({str(target)!r}))\n'
               'except PluginScanBlocked as exc:\n'
               ' assert "caution" in str(exc).lower(), str(exc)\n'
               'else:\n'
               ' raise AssertionError("Unconfirmed caution update must be refused")')
        assert installed_bytes() == installed_before
        assert databases[0].read_bytes() == before
        native('from hermes_cli.plugins_transaction import update_plugin; from pathlib import Path; '
               f'print(update_plugin(Path({str(target)!r}), force=True))')
        reconcile()
        assert (desktop/'plugin.js').read_bytes() == (fixture/'desktop/plugin.js').read_bytes()
        assert databases[0].read_bytes() == before
        native('from hermes_cli.plugins_cmd_remove import cmd_remove; cmd_remove("delivery-shelf")')
        assert not target.exists()
        reconcile()
        assert not desktop.exists()
        assert databases[0].read_bytes() == before
        print('PASS: native install/enable/disable/update/remove; Desktop copy/update/prune; retained SQLite bytes.')


if __name__ == '__main__':
    main()
