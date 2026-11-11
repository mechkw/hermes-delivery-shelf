"""Exercise the Saved server's real setup; never import a native/live host."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
IDS = ('conversation-bookmarks', 'delivery-shelf')
NAMES = (
    ('hermes-conversation-bookmarks', 'hermes-delivery-shelf'),
    ('hermes-conversation-bookmarks', 'hermes-delivery-shelf-egm'),
    ('checkout-a', 'checkout-b'),
)
SCENARIOS = (
    'both', 'conversation-bookmarks-only', 'delivery-shelf-only',
    'conversation-bookmarks-disabled', 'delivery-shelf-disabled', 'both-disabled',
    'ui-both--conversation-bookmarks-disabled', 'ui-both--delivery-shelf-disabled',
    'ui-both--both-disabled', 'ui-bookmarks--both', 'ui-shelf--both',
)


class SetupComplete(BaseException):
    """Stop after actual fixture copies/config/database, before native host import."""


class SavedFixtureReposTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='saved-identities-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.qa = self.base / 'qa'
        self.qa.mkdir()

    def repo(self, path, identity):
        path.mkdir(parents=True)
        (path / 'plugin.yaml').write_text('name: ' + identity + '\n')
        for file in ('__init__.py', 'telegram_shelf.py', 'recent_artifacts.py'):
            (path / file).write_text('# fictional ' + identity + '\n')
        for folder in ('dashboard', 'desktop'):
            (path / folder).mkdir()
            (path / folder / 'identity.txt').write_text(identity)
        return path

    def run_setup(self, root, peer, scenario='both', invalid=False):
        observed = []

        def stop(home):
            mode, state = scenario.split('--', 1) if '--' in scenario else ('matched', scenario)
            installed = [state.removesuffix('-only')] if state.endswith('-only') else list(IDS)
            disabled = list(IDS) if state == 'both-disabled' else ([state.removesuffix('-disabled')] if state.endswith('-disabled') else [])
            enabled = [name for name in installed if name not in disabled]
            self.assertEqual(sorted(p.name for p in (home / 'plugins').iterdir()), sorted(installed))
            for name in installed:
                target = home / 'plugins' / name
                self.assertEqual((target / 'plugin.yaml').read_text(), 'name: ' + name + '\n')
                for folder in ('dashboard', 'desktop'):
                    self.assertEqual((target / folder / 'identity.txt').read_text(), name)
                self.assertEqual((target / 'recent_artifacts.py').read_text(), '# fictional ' + name + '\n')
            import yaml
            self.assertEqual(yaml.safe_load((home / 'config.yaml').read_text())['plugins'],
                             {'isolation': 'in_process', 'enabled': enabled, 'disabled': disabled})
            self.assertTrue((home / 'state.db').is_file())
            self.assertEqual((home / 'workspaces' / 'example.md').read_text(), 'Fictional Saved delivery.\n')
            observed.append(True)
            raise SetupComplete()

        probe = types.ModuleType('native_probe')
        vars(probe).update(ROOT=root, host=stop)
        env = dict(os.environ)
        env.pop('SAVED_PEER_REPO', None)
        if peer is not None:
            env['SAVED_PEER_REPO'] = str(peer)
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {'native_probe': probe}), \
                patch.object(sys, 'argv', ['saved_browser_server.py', '0', str(self.qa), scenario]), \
                patch.object(sys, 'path', [str(HERE), *sys.path]), \
                patch('shutil.copy2', wraps=shutil.copy2) as copy_file, \
                patch('shutil.copytree', wraps=shutil.copytree) as copy_tree, \
                patch('tempfile.TemporaryDirectory', wraps=tempfile.TemporaryDirectory) as temporary:
            if invalid:
                with self.assertRaisesRegex(ValueError, 'Saved repositories'):
                    runpy.run_path(str(HERE / 'saved_browser_server.py'), run_name='__main__')
                copy_file.assert_not_called()
                copy_tree.assert_not_called()
                temporary.assert_not_called()
                self.assertFalse(observed)
            else:
                with self.assertRaises(SetupComplete):
                    runpy.run_path(str(HERE / 'saved_browser_server.py'), run_name='__main__')
                self.assertEqual(observed, [True])
                self.assertTrue(copy_file.called and copy_tree.called)
        self.assertEqual(list(self.qa.iterdir()), [])

    def test_explicit_checkout_names_and_scenarios(self):
        for index, names in enumerate(NAMES):
            repos = [self.repo(self.base / str(index) / name, identity) for name, identity in zip(names, IDS)]
            for root, peer in (repos, repos[::-1]):
                for scenario in SCENARIOS:
                    with self.subTest(root=root.name, scenario=scenario):
                        self.run_setup(root, peer, scenario)

    def test_default_peer_uses_manifest_not_root_basename(self):
        for index, names in enumerate(NAMES):
            for identity, name in zip(IDS, names):
                parent = self.base / str(index) / identity
                root = self.repo(parent / name, identity)
                other = next(i for i in IDS if i != identity)
                self.repo(parent / ('hermes-' + other), other)
                with self.subTest(root=root.name, identity=identity):
                    self.run_setup(root, None)

    def test_invalid_identities_rejected_before_any_fixture_write(self):
        cases = ('missing-root-manifest', 'missing-peer-manifest', 'missing-root-name',
                 'missing-peer-name', 'wrong-root-name', 'wrong-peer-name', 'duplicate-name',
                 'malformed-yaml', 'non-mapping', 'non-string-name', 'padded-name', 'same-path')
        for case in cases:
            parent = self.base / case
            root = self.repo(parent / 'hermes-delivery-shelf', 'delivery-shelf')
            peer = self.repo(parent / 'hermes-conversation-bookmarks', 'conversation-bookmarks')
            if case.startswith('missing-') and case.endswith('-manifest'):
                ((root if '-root-' in case else peer) / 'plugin.yaml').unlink()
            elif case.startswith('missing-'):
                ((root if '-root-' in case else peer) / 'plugin.yaml').write_text('version: 1\n')
            elif case.startswith('wrong-'):
                ((root if '-root-' in case else peer) / 'plugin.yaml').write_text('name: unrelated-plugin\n')
            elif case == 'duplicate-name':
                (peer / 'plugin.yaml').write_text('name: delivery-shelf\n')
            elif case == 'same-path':
                peer = root
            else:
                (peer / 'plugin.yaml').write_text({'malformed-yaml': 'name: [\n', 'non-mapping': '[]\n',
                    'non-string-name': 'name: [conversation-bookmarks]\n', 'padded-name': 'name: " conversation-bookmarks "\n'}[case])
            for scenario in ('both', 'delivery-shelf-only'):
                with self.subTest(case=case, scenario=scenario):
                    self.run_setup(root, peer, scenario, invalid=True)

    def node_repos(self, root, peer=None):
        # Import the exact helper consumed by saved-browser.mjs, not a test parser.
        program = """import {savedRepos, savedRoleFiles} from './saved-repos.mjs';
const repos=savedRepos(process.argv[1],process.argv[2]);
console.log(JSON.stringify({repos,files:Object.fromEntries(Object.keys(repos).map(id=>[id,savedRoleFiles(id)]))}));"""
        env = {**os.environ, 'PYTHON': sys.executable, 'PYTHONDONTWRITEBYTECODE': '1'}
        env.pop('SAVED_PEER_REPO', None)
        return subprocess.run(['node', '--input-type=module', '-e', program, str(root), *([str(peer)] if peer else [])],
                              cwd=HERE, env=env, text=True, capture_output=True)

    def test_node_consumer_mapping_and_role_pins(self):
        for index, names in enumerate(NAMES):
            repos = [self.repo(self.base / str(index) / name, identity) for name, identity in zip(names, IDS)]
            for root, peer in (repos, repos[::-1]):
                with self.subTest(root=root.name):
                    result = self.node_repos(root, peer)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    data = json.loads(result.stdout)
                    self.assertEqual(data['repos'], dict(zip(IDS, map(str, repos))))
                    self.assertEqual(data['files'], {'conversation-bookmarks': ['ui/Bookmarks.jsx', 'ui/BookmarkEditor.jsx'],
                                                     'delivery-shelf': ['ui/Shelf.jsx']})

    def test_node_default_peer_and_rejection(self):
        for identity in IDS:
            root = self.repo(self.base / identity / 'arbitrary-checkout', identity)
            other = next(i for i in IDS if i != identity)
            peer = self.repo(root.parent / ('hermes-' + other), other)
            # CI exports its real peer; default-location tests must use only
            # their own fictional pair, never this inherited override.
            with self.subTest(identity=identity), patch.dict(
                    os.environ, {'SAVED_PEER_REPO': str(self.base / 'not-a-fixture-peer')}):
                result = self.node_repos(root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['repos'][other], str(peer))
                for manifest in (None, 'name: unrelated-plugin\n', 'name: ' + identity + '\n'):
                    if manifest is None:
                        (peer / 'plugin.yaml').unlink()
                    else:
                        (peer / 'plugin.yaml').write_text(manifest)
                    result = self.node_repos(root, peer)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Saved repositories', result.stderr)
                    self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
