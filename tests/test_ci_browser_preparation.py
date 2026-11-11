"""No-install entrypoint contracts for disposable CI prerequisite preparation.

Every git, npm, pip and node call is a sentinel over fictional local inputs.
These tests prove refusal order/command planning, not a dependency installation.
"""
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1]/'scripts/prepare-ci-browser.py'
PATH_KEYS = ('HOME', 'HERMES_HOME', 'XDG_CACHE_HOME', 'HERMES_RUNTIME_DIR',
             'PLAYWRIGHT_BROWSERS_PATH', 'npm_config_cache', 'UV_CACHE_DIR')


class PreparationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ci-preparation-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        bank = Path(self.temp.name)
        self.scratch = bank/'scratch'
        self.host = self.scratch/'hermes'
        self.peer = self.scratch/'hermes-conversation-bookmarks'
        self.root = bank/'shelf'
        self.outside = bank/'outside'
        self.prefix = self.scratch/'test-venv'
        for directory in (self.host, self.peer, self.root, self.outside, self.prefix/'bin'):
            directory.mkdir(parents=True)
        self.base_python = self.outside/'python'
        self.base_python.write_text('fictional interpreter sentinel; never executed\n')
        self.executable = self.prefix/'bin/python'
        self.executable.symlink_to(self.base_python)
        (self.prefix/'pyvenv.cfg').write_text('home = '+str(self.outside)+'\n')
        for folder in (self.root, self.peer):
            (folder/'ui').mkdir()
            for name in ('Saved.jsx', 'saved-coordinator.js', 'saved.css'):
                (folder/'ui'/name).write_text('fictional shared protocol\n')
        self.host.joinpath('uv.lock').write_text('\n'.join(
            '[[package]]\nname = "'+name+'"\nversion = "1.0.0"'
            for name in ('openai', 'distro', 'jiter', 'sniffio', 'tqdm')))
        self.env = dict(TMPDIR=str(self.scratch), HERMES_SOURCE=str(self.host),
                        HOME=str(self.scratch/'account'), HERMES_HOME=str(self.scratch/'account/.hermes'),
                        XDG_CACHE_HOME=str(self.scratch/'cache'), HERMES_RUNTIME_DIR=str(self.scratch/'runtime'),
                        PLAYWRIGHT_BROWSERS_PATH=str(self.scratch/'browsers'),
                        npm_config_cache=str(self.scratch/'cache/npm'), UV_CACHE_DIR=str(self.scratch/'cache/uv'))
        self.globals = runpy.run_path(str(HELPER))['main'].__globals__
        self.commands = []
        self.git_reads = []
        def git(repo, *args):
            self.git_reads.append((str(repo), args))
            if args[0] == 'status':
                return ''
            if args[0] == 'remote':
                return self.globals['PEER_URL']
            return self.globals['HOST_COMMIT'] if Path(repo) == self.host else self.globals['PEER_COMMIT']
        def run(*args, **kwargs):
            self.commands.append((args, str(kwargs.get('cwd', self.root))))
        self.globals.update(ROOT=self.root, git=git, run=run)

    def invoke(self, **runtime):
        values = dict(prefix=str(self.prefix), exec_prefix=str(self.prefix),
                      base_prefix=str(self.outside), executable=str(self.executable))
        values.update(runtime)
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, self.env, clear=True))
            for name, value in values.items():
                stack.enter_context(patch.object(sys, name, value))
            stack.enter_context(patch('subprocess.check_output', return_value='v22.fictional-sentinel\n'))
            self.globals['main']()

    def refused(self, message, **runtime):
        with self.assertRaisesRegex(SystemExit, message):
            self.invoke(**runtime)
        self.assertEqual(self.commands, [], 'No mutation/build command may precede refusal')
        self.assertEqual(self.git_reads, [], 'All disposable path checks precede even git inspection')

    def test_legitimate_disposable_venv_allows_base_interpreter_symlink(self):
        self.invoke()
        pip = [args for args, cwd in self.commands if args[:3] == (str(self.executable), '-m', 'pip')]
        self.assertEqual(len(pip), 2)
        self.assertIn('--no-deps', pip[0])
        self.assertEqual(pip[1][-1], 'check')
        self.assertTrue((self.scratch/'ci-browser-inputs.json.gz').is_file())
        self.assertEqual(self.executable.resolve(), self.base_python)

    def test_legitimate_missing_peer_reaches_only_planned_local_creation(self):
        import shutil
        shutil.rmtree(self.peer)
        class CreationReached(Exception):
            pass
        def stop(*args, **kwargs):
            self.commands.append((args, str(kwargs.get('cwd', self.root))))
            raise CreationReached()
        self.globals['run'] = stop
        with self.assertRaises(CreationReached):
            self.invoke()
        self.assertEqual(self.commands[0][0], ('git', 'init', str(self.peer)))

    def test_tmpdir_must_be_explicit_existing_and_not_a_filesystem_root(self):
        for invalid in (None, 'relative-scratch', str(self.outside/'missing'), '/'):
            with self.subTest(path=invalid):
                saved = self.env.pop('TMPDIR')
                if invalid is not None:
                    self.env['TMPDIR'] = invalid
                try:
                    self.refused('TMPDIR')
                finally:
                    self.env['TMPDIR'] = saved

    def test_external_interpreter_refused(self):
        self.refused('virtual environment', prefix=str(self.outside), exec_prefix=str(self.outside))

    def test_scratch_root_cannot_be_the_venv(self):
        self.refused('virtual environment', prefix=str(self.scratch), exec_prefix=str(self.scratch))

    def test_base_interpreter_refused(self):
        self.refused('virtual environment', base_prefix=str(self.prefix))

    def test_missing_venv_identity_refused(self):
        (self.prefix/'pyvenv.cfg').unlink()
        self.refused('pyvenv.cfg')

    def test_symlinked_venv_identity_refused(self):
        cfg = self.prefix/'pyvenv.cfg'
        cfg.unlink()
        cfg.symlink_to(self.base_python)
        self.refused('pyvenv.cfg')

    def test_unrelated_executable_refused(self):
        self.refused('executable', executable=str(self.base_python))

    def test_mismatched_exec_prefix_refused(self):
        self.refused('virtual environment', exec_prefix=str(self.outside))

    def test_external_peer_symlink_refused(self):
        import shutil
        shutil.rmtree(self.peer)
        self.peer.symlink_to(self.outside, target_is_directory=True)
        self.refused('Bookmarks peer')

    def test_dangling_external_peer_symlink_refused(self):
        import shutil
        shutil.rmtree(self.peer)
        self.peer.symlink_to(self.outside/'missing', target_is_directory=True)
        self.refused('Bookmarks peer')

    def test_external_host_refused(self):
        self.env['HERMES_SOURCE'] = str(self.outside)
        self.refused('HERMES_SOURCE')

    def test_all_explicit_paths_required(self):
        for key in PATH_KEYS:
            with self.subTest(key=key):
                saved = self.env.pop(key)
                try:
                    self.refused(key)
                finally:
                    self.env[key] = saved

    def test_all_explicit_paths_must_be_absolute_and_strictly_inside_scratch(self):
        for key in PATH_KEYS:
            for invalid in (str(self.outside), str(self.scratch), 'relative-cache'):
                with self.subTest(key=key, path=invalid):
                    saved = self.env[key]
                    self.env[key] = invalid
                    try:
                        self.refused(key)
                    finally:
                        self.env[key] = saved

    def test_cache_symlink_escape_refused(self):
        escape = self.scratch/'escape-cache'
        escape.symlink_to(self.outside, target_is_directory=True)
        self.env['npm_config_cache'] = str(escape)
        self.refused('npm_config_cache')


if __name__ == '__main__':
    unittest.main(verbosity=2)
