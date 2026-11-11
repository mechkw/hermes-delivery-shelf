"""Inspect/revoke existing agent consent; granting belongs to a concrete version offer."""
import sqlite3
from fastapi import HTTPException


def permission(store, entry_id, *, revoke=False):
    entry = store.get(entry_id)  # A real deliberately saved delivery is required.
    path = store.home / 'plugin-data/delivery-shelf/agent-links.sqlite3'
    if path.is_symlink():
        raise HTTPException(503, 'Agent permission storage is unsafe')
    always = False
    if path.exists():
        try:
            with sqlite3.connect(path, timeout=2) as conn:
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='version_permissions'").fetchone()
                if exists:
                    if revoke:
                        # Desktop is the profile owner: revoke all transport owners for this delivery.
                        conn.execute('DELETE FROM version_permissions WHERE entry_id=?', (entry_id,))
                    always = conn.execute('SELECT 1 FROM version_permissions WHERE entry_id=? LIMIT 1', (entry_id,)).fetchone() is not None
        except sqlite3.Error:
            raise HTTPException(503, 'Agent permission storage is unavailable') from None
    return {'always': always, 'paused': entry.get('state', 'active') != 'active'}
