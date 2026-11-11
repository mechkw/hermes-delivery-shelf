"""Manifest-backed identities shared by the Saved browser runner and server."""
import json
from pathlib import Path
import sys

import yaml


IDS = ('conversation-bookmarks', 'delivery-shelf')


def plugin_id(repo):
    manifest = repo / 'plugin.yaml'
    try:
        data = yaml.safe_load(manifest.read_text())
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError(f'Saved repositories: cannot read plugin identity from {manifest}') from error
    name = data.get('name') if isinstance(data, dict) else None
    if not isinstance(name, str) or name not in IDS:
        raise ValueError(f'Saved repositories: expected a supported plugin name in {manifest}, got {name!r}')
    return name


def saved_repos(root, peer=None):
    """Validate the complete pair before the caller creates/copies any fixture.

    Insertion order is root then peer; directory basenames are never identities.
    Only the conventional *default peer location* uses a repository folder name.
    """
    root = Path(root).resolve()
    root_id = plugin_id(root)
    other_id = next(name for name in IDS if name != root_id)
    peer = Path(peer).resolve() if peer is not None else root.parent / ('hermes-' + other_id)
    peer_id = plugin_id(peer)
    if peer_id != other_id:
        raise ValueError(f'Saved repositories: duplicate identity {peer_id!r} in {root} and {peer}; expected {other_id!r}')
    return {root_id: root, peer_id: peer}


if __name__ == '__main__':
    repos = saved_repos(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps({name: str(repo) for name, repo in repos.items()}))
