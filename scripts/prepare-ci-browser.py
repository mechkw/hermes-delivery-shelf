#!/usr/bin/env python3
"""Prepare pinned public browser inputs, only inside the disposable CI bank.

No host activation, provider requests, live checkout fallback or peer overlays.
Run after npm ci and installation of tests/requirements-ci.txt into PYTHON.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

HOST_COMMIT = 'bf0203a794a07aac3ff764972ab9087baa4e4f4e'
PEER_COMMIT = '3f70841a5037c31bfa03234331dc88528c5911e5'
PEER_URL = 'https://github.com/mechkw/hermes-conversation-bookmarks.git'
ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    subprocess.run(args, cwd=cwd, check=True)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def inventory(root):
    """Conservative superset: source, installed dependencies and generated CSS.

    Do not traverse directory symlinks. Record their targets, plus each actual
    regular file. npm workspace targets are independently included in the tree.
    """
    files, links = {}, {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(n for n in dirs if n not in ('.git', '__pycache__', '.cache'))
        for name in sorted([*dirs, *names]):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                links[relative] = os.readlink(path)
            elif path.is_file():
                files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'root': str(root), 'files': files, 'symlinks': links}


def disposable_path(raw, label, scratch):
    """Resolve absent leaves too: a dangling symlink must not escape the bank."""
    if not raw or not Path(raw).is_absolute():
        raise SystemExit(label+' must be an explicit absolute path beneath TMPDIR')
    path = Path(raw).resolve()
    if path == scratch or not path.is_relative_to(scratch):
        raise SystemExit(label+' must be strictly beneath TMPDIR (no symlink escape)')
    return path


def preparation_paths():
    """Validate every mutation destination before inspecting or building repos.

    A venv's python binary normally symlinks to the base interpreter outside the
    bank. Its active prefix, pyvenv marker and executable *directory* identify
    the installation target; resolving the binary itself would reject valid CI.
    This is a preflight for owned CI inputs, not a sandbox against path races.
    """
    raw = os.environ.get('TMPDIR')
    if not raw or not Path(raw).is_absolute():
        raise SystemExit('TMPDIR must be an explicit absolute disposable directory')
    scratch = Path(raw).resolve()
    if scratch == Path(scratch.anchor) or not scratch.is_dir():
        raise SystemExit('TMPDIR must be an existing disposable directory, not a filesystem root')
    prefix = disposable_path(sys.prefix, 'Python virtual environment', scratch)
    if prefix == Path(sys.base_prefix).resolve() or Path(sys.exec_prefix).resolve() != prefix:
        raise SystemExit('Python virtual environment must be active beneath TMPDIR')
    marker = prefix/'pyvenv.cfg'
    if marker.is_symlink() or not marker.is_file():
        raise SystemExit('Python virtual environment needs its own regular pyvenv.cfg')
    bindir = prefix/('Scripts' if os.name == 'nt' else 'bin')
    if not Path(sys.executable).is_absolute() or Path(sys.executable).parent.resolve() != bindir:
        raise SystemExit('Python executable must belong to the disposable virtual environment')
    for name in ('HOME', 'HERMES_HOME', 'XDG_CACHE_HOME', 'HERMES_RUNTIME_DIR',
                 'PLAYWRIGHT_BROWSERS_PATH', 'npm_config_cache', 'UV_CACHE_DIR'):
        disposable_path(os.environ.get(name), name, scratch)
    host = disposable_path(os.environ.get('HERMES_SOURCE'), 'HERMES_SOURCE', scratch)
    peer = disposable_path(str(scratch/'hermes-conversation-bookmarks'), 'Bookmarks peer', scratch)
    return scratch, host, peer


def main():
    scratch, host, peer = preparation_paths()
    if git(host, 'rev-parse', 'HEAD') != HOST_COMMIT:
        raise SystemExit('Unexpected official host revision')
    if git(host, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Official host tracked inputs are dirty')
    if not peer.exists():
        run('git', 'init', str(peer))
        run('git', '-C', str(peer), 'remote', 'add', 'origin', PEER_URL)
        run('git', '-C', str(peer), 'fetch', '--depth=1', 'origin', PEER_COMMIT)
        run('git', '-C', str(peer), 'checkout', '--detach', 'FETCH_HEAD')
    if git(peer, 'remote', 'get-url', 'origin') != PEER_URL or git(peer, 'rev-parse', 'HEAD') != PEER_COMMIT:
        raise SystemExit('Unexpected public Bookmarks peer source/revision')
    if git(peer, 'status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('Public Bookmarks peer tracked inputs are dirty')
    # Validate the shared protocol, not the peer's unused server fixture.
    for name in ('ui/Saved.jsx', 'ui/saved-coordinator.js', 'ui/saved.css'):
        if (ROOT/name).read_bytes() != (peer/name).read_bytes():
            raise SystemExit('Paired Saved shared protocol differs: '+name)
    run('npm', 'ci', '--ignore-scripts', cwd=peer)
    run('npm', 'run', 'build', cwd=peer)
    run('npm', 'ci', '--ignore-scripts', cwd=host)
    # Only the renderer CSS is consumed; do not build/launch Electron or native
    # helpers. Use the official pinned workspace's Vite/Tailwind configuration.
    run('npm', 'exec', '--workspace', 'apps/desktop', '--', 'vite', 'build', '--configLoader', 'runner', cwd=host)
    # The cold-serve regression uses the real auxiliary HTTP client against a
    # loopback fictional provider. requirements-ci intentionally omits that SDK.
    # Add only its missing transport closure, pinned by this official uv.lock;
    # --no-deps leaves every exact requirements-ci version unchanged.
    packages = {p['name']: p for p in tomllib.loads((host/'uv.lock').read_text())['package']}
    transport = [name+'=='+packages[name]['version'] for name in ('openai', 'distro', 'jiter', 'sniffio', 'tqdm')]
    run(sys.executable, '-m', 'pip', 'install', '--no-deps', *transport)
    run(sys.executable, '-m', 'pip', 'check')
    for repo in (host, peer):
        if git(repo, 'status', '--porcelain', '--untracked-files=no'):
            raise SystemExit('Preparation modified tracked source: '+str(repo))
    # Fail on SDK/export or stylesheet incompatibility before any test fixture.
    run('node', '--input-type=module', '-e',
        "import {realUI} from './tests/native-components.mjs'; await realUI(process.env.HERMES_SOURCE)")
    record = {'hostCommit': HOST_COMMIT, 'peerCommit': PEER_COMMIT,
              'peerURL': PEER_URL, 'transportPins': transport,
              'python': sys.version, 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
              'inputs': {name: inventory(path) for name, path in
                         [('shelf', ROOT), ('peer', peer), ('host', host),
                          ('python', Path(sys.prefix))]}}
    with gzip.open(scratch/'ci-browser-inputs.json.gz', 'wt') as stream:
        json.dump(record, stream, sort_keys=True)
    # The caller owns env propagation. Never use an implicit adjacent peer.
    print('SAVED_PEER_REPO='+str(peer), flush=True)
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'], 'a') as stream:
            stream.write('SAVED_PEER_REPO='+str(peer)+'\n')


if __name__ == '__main__':
    main()
