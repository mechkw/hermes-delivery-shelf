"""Additive shelf lifecycle schema and transactional state transitions."""
import time

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

State = Literal['active', 'archived', 'trash', 'pending_delete', 'all']
STATE_SQL = "coalesce((SELECT state FROM entry_lifecycle WHERE entry_id=entries.id),'active')"


class EntryFilter(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    q: str = Field(default='', max_length=200)
    tag: str = Field(default='', max_length=40)
    kind: str = Field(default='', max_length=40)
    project: str = Field(default='', max_length=100)
    state: State = 'active'


class BulkAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    action: Literal['archive', 'trash', 'restore', 'empty_trash']
    ids: list[str] | None = Field(default=None, min_length=1, max_length=10000)
    filter: EntryFilter | None = None

    @model_validator(mode='after')
    def exact_selection(self):
        import re
        if (self.ids is None) == (self.filter is None):
            raise ValueError('Supply either ids or filter')
        if self.ids and (len(set(self.ids)) != len(self.ids) or any(not re.fullmatch('[a-f0-9]{32}', value) for value in self.ids)):
            raise ValueError('Select unique delivery IDs')
        return self


def initialize(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS entry_lifecycle (entry_id TEXT PRIMARY KEY REFERENCES entries(id) ON DELETE CASCADE, state TEXT NOT NULL, trashed_at REAL, delete_after REAL)")
    conn.execute('CREATE TABLE IF NOT EXISTS managed_purge_jobs (version_id TEXT PRIMARY KEY, bytes INTEGER NOT NULL, files INTEGER NOT NULL)')


def fields(conn, entry_id):
    row = conn.execute('SELECT state,trashed_at,delete_after FROM entry_lifecycle WHERE entry_id=?', (entry_id,)).fetchone()
    return dict(row) if row else {'state': 'active', 'trashed_at': None, 'delete_after': None}


def transition(store, conn, rows, action, *, revision=None):
    now = time.time()
    retention = store.settings()['trash_retention_days']
    result = []
    for row in rows:
        current = fields(conn, row['id'])
        if revision is not None and row['revision'] != revision:
            raise HTTPException(409, 'Delivery changed elsewhere; refresh before removing')
        state = current['state']
        if action == 'trash' and state == 'pending_delete':
            raise HTTPException(409, 'Restore this delivery before moving it to trash again')
        if action == 'empty_trash' and state != 'trash':
            raise HTTPException(409, 'Only trash can be emptied')
        if action == 'archive' and state not in ('active', 'archived'):
            raise HTTPException(409, 'Restore this delivery before archiving')
        if action == 'restore' and current['delete_after'] is not None and now >= current['delete_after']:
            raise HTTPException(409, 'Recovery deadline has passed')
        target = {'archive': 'archived', 'restore': 'active', 'trash': 'trash', 'empty_trash': 'pending_delete'}[action]
        if target != state:
            trashed_at = now if action == 'trash' else current['trashed_at'] if action == 'empty_trash' else None
            deadline = now + retention * 86400 if action == 'trash' else now + 3600 if action == 'empty_trash' else None
            conn.execute('INSERT INTO entry_lifecycle VALUES (?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET state=excluded.state,trashed_at=excluded.trashed_at,delete_after=excluded.delete_after', (row['id'], target, trashed_at, deadline))
            conn.execute('UPDATE entries SET updated=?,revision=revision+1 WHERE id=?', (now, row['id']))
        result.append(store.decode(conn.execute('SELECT * FROM entries WHERE id=?', (row['id'],)).fetchone(), conn))
    return {'items': result, 'affected': len(result)}


def cleanup(store, *, now=None, force=False):
    """Commit a durable purge queue before unlinking; failed unlinks retry later.

    Reserve SQLite through each unlink so concurrent cleanup workers cannot
    acknowledge a failed job. No source paths are ever passed to purge().
    """
    import json
    now = time.time() if now is None else now
    purged = 0
    with store.writing() as (conn, _):
        enabled = store.settings()['auto_cleanup']
        if enabled or force:
            rows = conn.execute("SELECT entry_id FROM entry_lifecycle WHERE state IN ('trash','pending_delete') AND delete_after<=?", (now,)).fetchall()
            for row in rows:
                for version in conn.execute('SELECT id,files FROM entry_versions WHERE entry_id=?', (row['entry_id'],)):
                    files = json.loads(version['files'])
                    conn.execute('INSERT OR IGNORE INTO managed_purge_jobs VALUES (?,?,?)', (version['id'], sum(f['size'] for f in files), len(files)))
                conn.execute('DELETE FROM entries WHERE id=?', (row['entry_id'],))
            purged = len(rows)
    failures = []
    with store.writing() as (conn, _):
        # Already-committed jobs finish even if automatic scheduling is disabled.
        for row in conn.execute('SELECT version_id FROM managed_purge_jobs').fetchall():
            try:
                store.managed().purge(row['version_id'])
            except (OSError, ValueError):
                failures.append(row['version_id'])
            else:
                conn.execute('DELETE FROM managed_purge_jobs WHERE version_id=?', (row['version_id'],))
        pending = conn.execute('SELECT count(*) FROM managed_purge_jobs').fetchone()[0]
    return {'purged': purged, 'pending_purges': pending, 'failed_versions': failures, 'skipped': not enabled and not force}


def storage(store):
    """Managed payload bytes only; originals/DB/preview-cache are not counted."""
    import json
    states = {state: dict(bytes=0, entries=0, files=0) for state in ('active', 'archived', 'trash', 'pending_delete')}
    with store.connect() as conn:
        # One consistent SQLite read snapshot for entries, versions and jobs.
        conn.execute('BEGIN')
        for row in conn.execute('SELECT id FROM entries'):
            counts = states[fields(conn, row['id'])['state']]
            counts['entries'] += 1
            for version in conn.execute('SELECT files FROM entry_versions WHERE entry_id=?', (row['id'],)):
                files = json.loads(version['files'])
                counts['bytes'] += sum(item['size'] for item in files)
                counts['files'] += len(files)
        pending = conn.execute('SELECT count(*),coalesce(sum(bytes),0),coalesce(sum(files),0) FROM managed_purge_jobs').fetchone()
    return dict(states=states, total_bytes=sum(v['bytes'] for v in states.values()) + pending[1],
                total_entries=sum(v['entries'] for v in states.values()),
                total_files=sum(v['files'] for v in states.values()) + pending[2],
                pending_purges=pending[0], pending_purge_bytes=pending[1],
                scope='managed_payloads')
