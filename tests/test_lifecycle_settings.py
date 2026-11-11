"""Real API/catalog lifecycle contracts, isolated from installed profiles."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('lifecycle_contract_api', Path(__file__).parents[1] / 'dashboard/plugin_api.py')
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    home = tmp_path / 'profile'
    (home / 'workspaces').mkdir(parents=True)
    monkeypatch.setattr(api, 'bound_home', lambda: home)
    return api.Store(home)


def client(shelf):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.request_store] = lambda: shelf
    return TestClient(app)


def saved(shelf, name='report.txt', **metadata):
    path = shelf.home / 'workspaces' / name
    path.write_bytes(b'original')
    return shelf.create(api.EntryInput(title=name, file=api.FileRef(root='workspaces', path=name), **metadata))


def test_archive_restore_and_safe_delete_preserve_versions(shelf):
    item = saved(shelf)
    http = client(shelf)
    result = http.post('/entries/bulk-action', json={'action': 'archive', 'ids': [item['id']]} )
    assert result.status_code == 200, result.text
    archived = result.json()['items'][0]
    assert archived['state'] == 'archived' and archived['revision'] == 2
    assert archived['versions'] == item['versions']
    assert shelf.search()['total'] == 0
    assert http.get('/entries', params={'state': 'archived'}).json()['total'] == 1
    result = http.post('/entries/bulk-action', json={'action': 'restore', 'ids': [item['id']]})
    assert result.json()['items'][0]['state'] == 'active'
    result = http.delete(f"/entries/{item['id']}", params={'revision': 3})
    assert result.status_code == 200, result.text
    trashed = shelf.get(item['id'])
    assert trashed['state'] == 'trash'
    assert trashed['delete_after'] - trashed['trashed_at'] == 60 * 86400
    assert api.read_entry_file(shelf, trashed)[1] == b'original'
    assert http.delete(f"/entries/{item['id']}", params={'revision': 3}).status_code == 409


def test_settings_validation_migrates_generation_and_changes_existing_trash(shelf):
    with shelf.connect() as conn:
        conn.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value INTEGER NOT NULL)')
        conn.execute("INSERT INTO settings VALUES ('previous_exchanges',20)")
    item = saved(shelf)
    shelf.bulk_action({'action': 'trash', 'ids': [item['id']]})
    http = client(shelf)
    response = http.get('/settings')
    assert response.status_code == 200, response.text
    defaults = response.json()
    assert defaults == dict(trash_retention_days=60, auto_cleanup=True, timezone='auto', hour_cycle='auto',
                           date_format='medium', default_view='together', enabled_views=['together','library','gallery'],
                           generate_metadata=True, context_messages=20)
    changed = http.put('/settings', json={'trash_retention_days':30, 'timezone':'America/New_York', 'context_messages':5})
    assert changed.status_code == 200, changed.text
    assert shelf.get(item['id'])['delete_after'] - shelf.get(item['id'])['trashed_at'] == 30 * 86400
    assert api.Store(shelf.home).settings() == changed.json()
    assert http.get('/generation/settings').json() == {'previous_exchanges':5}
    assert http.put('/generation/settings', json={'previous_exchanges':50}).status_code == 200
    assert http.get('/settings').json()['context_messages'] == 50
    for payload in ({'trash_retention_days':31}, {'auto_cleanup':1}, {'enabled_views':[]},
                    {'enabled_views':['gallery']}, {'timezone':'Fictional/Zone'}, {'context_messages':11},
                    {'auto_save':True}, {'hour_cycle':'25'}, {'date_format':'bad'}):
        assert http.put('/settings', json=payload).status_code == 422, payload
    valid = http.put('/settings', json={'enabled_views':['gallery'], 'default_view':'gallery'})
    assert valid.status_code == 200


def test_empty_trash_recovery_and_real_deadline_purge_leave_originals(shelf, monkeypatch):
    clock = [1000000.0]
    monkeypatch.setattr(api.source_module('lifecycle').time, 'time', lambda: clock[0])
    item = saved(shelf)
    keep = saved(shelf, 'keep.txt')
    http = client(shelf)
    shelf.bulk_action({'action':'trash', 'ids':[item['id']]})
    pending = shelf.bulk_action({'action':'empty_trash', 'filter':{'state':'trash'}})['items'][0]
    assert pending['state'] == 'pending_delete' and pending['delete_after'] == clock[0] + 3600
    result = http.post('/cleanup')
    assert result.status_code == 200, result.text
    assert result.json()['purged'] == 0
    assert shelf.bulk_action({'action':'restore', 'ids':[item['id']]})['items'][0]['delete_after'] is None
    shelf.bulk_action({'action':'trash', 'ids':[item['id']]})
    shelf.bulk_action({'action':'empty_trash', 'ids':[item['id']]})
    clock[0] += 3600
    assert http.post('/entries/bulk-action', json={'action':'restore', 'ids':[item['id']]}).status_code == 409
    result = http.post('/cleanup').json()
    assert result['purged'] == 1 and result['pending_purges'] == 0
    assert not (shelf.managed().directory / item['current_version']).exists()
    assert (shelf.home / 'workspaces' / 'report.txt').read_bytes() == b'original'
    assert api.read_entry_file(shelf, shelf.get(keep['id']))[1] == b'original'
    assert http.get(f"/entries/{item['id']}").status_code == 404
    assert http.post('/cleanup').json()['purged'] == 0


def test_version_and_file_provenance_survive_metadata_edits_and_resume(shelf):
    path = shelf.home / 'workspaces' / 'v1.txt'
    path.write_bytes(b'first')
    ref = {'root':'workspaces', 'path':'v1.txt'}
    origin = {'message_id':11, 'digest':'a'*64, 'artifact_id':'b'*64}
    http = client(shelf)
    response = http.post('/entries', json={'title':'First', 'files':[ref], 'session_id':'chat-one',
                        'sources':[{'file':ref, 'source':origin}]})
    assert response.status_code == 201, response.text
    item = response.json()
    original = item['versions'][0]
    provenance = original['files'][0]['provenance']
    assert provenance == {'profile':'default', 'session_id':'chat-one', 'message_id':11,
                          'original_root':'workspaces', 'original_path':str(path), 'source':origin, 'known':True}
    assert original['provenance']['session_id'] == 'chat-one'
    next_path = shelf.home / 'workspaces' / 'v2.txt'
    next_path.write_bytes(b'second')
    next_ref = {'root':'workspaces', 'path':'v2.txt'}
    next_origin = {**origin, 'message_id':22}
    response = http.post(f"/entries/{item['id']}/versions", json={'revision':1, 'files':[next_ref],
             'session_id':'chat-two', 'sources':[{'file':next_ref, 'source':next_origin}]})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item['versions'][0] == original
    assert item['versions'][1]['files'][0]['provenance']['message_id'] == 22
    changed = shelf.update(item['id'], api.EntryUpdate(title='Metadata only', revision=2))
    assert changed['session_id'] == 'chat-two'
    assert changed['versions'] == item['versions']
    assert api.Store(shelf.home).get(item['id']) == changed
    bad = http.post(f"/entries/{item['id']}/versions", json={'revision':3, 'files':[next_ref],
                   'session_id':'chat-two', 'sources':[{'file':ref, 'source':origin}]})
    assert bad.status_code == 422
    assert shelf.get(item['id']) == changed


def test_legacy_version_migration_never_infers_old_provenance_from_latest_entry(shelf):
    item = saved(shelf, session_id='current-chat')
    with shelf.connect() as conn:
        version = item['versions'][0]
        files = [{key:value for key,value in f.items() if key != 'provenance'} for f in version['files']]
        conn.execute('UPDATE entry_versions SET files=? WHERE id=?', (json.dumps(files), version['id']))
        conn.execute('DELETE FROM version_provenance WHERE version_id=?', (version['id'],))
    legacy = api.Store(shelf.home).get(item['id'])['versions'][0]
    assert legacy['provenance']['known'] is False
    assert legacy['provenance']['session_id'] is None
    assert legacy['files'][0]['provenance']['original_path'] is None
    assert legacy['files'][0]['provenance']['message_id'] is None


def test_storage_counts_all_versions_and_retryable_purge_bytes(shelf, monkeypatch):
    item = saved(shelf)
    http = client(shelf)
    response = http.get('/storage')
    assert response.status_code == 200, response.text
    usage = response.json()
    assert usage['total_bytes'] == 8 and usage['total_entries'] == 1 and usage['total_files'] == 1
    assert usage['states']['active'] == {'bytes':8, 'entries':1, 'files':1}
    shelf.bulk_action({'action':'trash', 'ids':[item['id']]})
    shelf.save_settings({'auto_cleanup':False})
    deadline = shelf.get(item['id'])['delete_after']
    assert shelf.cleanup_due(now=deadline)['skipped'] is True
    assert shelf.get(item['id'])['state'] == 'trash'
    managed = api.source_module('managed_files').ManagedFiles
    real_purge = managed.purge
    def failed(self, version_id):
        raise OSError('read-only storage')
    monkeypatch.setattr(managed, 'purge', failed)
    result = shelf.cleanup_due(now=deadline, force=True)
    assert result['purged'] == 1 and result['pending_purges'] == 1
    assert shelf.storage()['pending_purge_bytes'] == 8
    assert shelf.storage()['total_bytes'] == 8
    monkeypatch.setattr(managed, 'purge', real_purge)
    result = api.Store(shelf.home).cleanup_due(now=deadline)
    assert result['pending_purges'] == 0
    assert shelf.storage()['total_bytes'] == 0
    assert (shelf.home / 'workspaces' / 'report.txt').exists()


def test_inactive_entries_reject_versions_and_never_leak_into_recent_context(shelf):
    item = saved(shelf)
    shelf.bulk_action({'action':'archive', 'ids':[item['id']]})
    http = client(shelf)
    result = http.post(f"/entries/{item['id']}/versions", json={'revision':2,'files':[item['file']]})
    assert result.status_code == 409, result.text
    assert shelf.recent_attached() == []
    assert len(shelf.get(item['id'])['versions']) == 1
    shelf.bulk_action({'action':'restore', 'ids':[item['id']]})
    shelf.bulk_action({'action':'trash', 'ids':[item['id']]})
    pending = shelf.bulk_action({'action':'empty_trash', 'ids':[item['id']]})['items'][0]
    assert http.post('/entries/bulk-action', json={'action':'trash','ids':[item['id']]}).status_code == 409
    assert shelf.get(item['id']) == pending


def test_bulk_filter_selects_every_match_not_just_visible_page_and_rolls_back(shelf):
    for i in range(105):
        shelf.create(api.EntryInput(title=f'Batch {i}', project='North', tags=['Équipe']))
    keep = shelf.create(api.EntryInput(title='Batch unrelated', project='South', tags=['Équipe']))
    assert shelf.search(project='North', limit=50)['total'] == 105
    result = shelf.bulk_action({'action':'archive', 'filter':{'q':'Batch', 'project':'North', 'tag':'éQUIPE'}})
    assert result['affected'] == len(result['items']) == 105
    assert shelf.search(state='archived')['total'] == 105
    assert shelf.search()['items'] == [keep]
    http = client(shelf)
    first = result['items'][0]
    # The first row is modified before the second transition refuses; DB must undo it.
    shelf.bulk_action({'action':'trash', 'ids':[first['id']]})
    keep_before = shelf.get(keep['id'])
    response = http.post('/entries/bulk-action', json={'action':'archive', 'ids':[keep['id'], first['id']]})
    assert response.status_code == 409
    assert shelf.get(keep['id']) == keep_before
    assert http.post('/entries/bulk-action', json={'action':'trash', 'ids':[keep['id'], 'f'*32]}).status_code == 404
    assert shelf.get(keep['id']) == keep_before
    for payload in ({'action':'trash'}, {'action':'purge','ids':[keep['id']]},
                    {'action':'trash','ids':[]}, {'action':'trash','ids':[keep['id'],keep['id']]},
                    {'action':'trash','ids':[keep['id']],'filter':{}},
                    {'action':'trash','filter':{'state':'fictional'}},
                    {'action':'trash','filter':{'offset':0}}):
        assert http.post('/entries/bulk-action', json=payload).status_code == 422, payload


def test_purge_all_versions_symlink_target_and_original_never_followed(shelf):
    item = saved(shelf)
    version_one = item['versions'][0]
    updated = shelf.add_version(item['id'], api.VersionInput(revision=1, files=[api.FileRef.model_validate(item['file'])]))
    outside = shelf.home / 'workspaces' / 'report.txt'
    folder = shelf.managed().directory / version_one['id']
    (folder / 'unexpected-link').symlink_to(outside)
    shelf.bulk_action({'action':'trash','ids':[item['id']]})
    deadline = shelf.get(item['id'])['delete_after']
    assert shelf.cleanup_due(now=deadline-0.01)['purged'] == 0
    assert shelf.cleanup_due(now=deadline)['purged'] == 1
    assert all(not (shelf.managed().directory / v['id']).exists() for v in updated['versions'])
    assert outside.read_bytes() == b'original'
    assert shelf.storage()['total_bytes'] == 0


def test_linked_managed_root_is_refused_and_job_retries_after_repair(shelf):
    item = saved(shelf)
    root = shelf.managed().directory
    escrow = root.with_name('escrow')
    root.rename(escrow)
    root.symlink_to(shelf.home / 'workspaces', target_is_directory=True)
    shelf.bulk_action({'action':'trash', 'ids':[item['id']]})
    deadline = shelf.get(item['id'])['delete_after']
    result = shelf.cleanup_due(now=deadline)
    assert result['pending_purges'] == 1
    assert (shelf.home / 'workspaces' / 'report.txt').read_bytes() == b'original'
    root.unlink()
    escrow.rename(root)
    assert api.Store(shelf.home).cleanup_due(now=deadline)['pending_purges'] == 0


def test_migration_preserves_exact_legacy_rows_and_pending_retention(shelf):
    legacy_id = 'a'*32
    payload = json.dumps({'title':' Legacy untouched ', 'file':None,'session_id':'legacy-chat','tags':[' A ','A'], 'kind':'document','project':'','description':''})
    with shelf.connect() as conn:
        conn.execute('INSERT INTO entries VALUES (?,?,?,?,?)', (legacy_id,payload,123,456,7))
    for _ in range(3):
        reopened = api.Store(shelf.home)
        item = reopened.get(legacy_id)
        assert (item['revision'],item['created'],item['updated'],item['state']) == (7,123,456,'active')
        with reopened.connect() as conn:
            assert tuple(conn.execute('SELECT * FROM entries WHERE id=?',(legacy_id,)).fetchone()) == (legacy_id,payload,123,456,7)
    item = saved(shelf)
    shelf.bulk_action({'action':'trash','ids':[item['id']]})
    pending = shelf.bulk_action({'action':'empty_trash','ids':[item['id']]})['items'][0]
    shelf.save_settings({'trash_retention_days':30})
    assert shelf.get(item['id']) == pending


def test_native_source_selection_cannot_claim_an_unvalidated_other_session(shelf):
    from hermes_state import SessionDB
    db = SessionDB(shelf.home / 'state.db')
    try:
        db.create_session('native-source', source='desktop')
        path = shelf.home / 'workspaces' / 'source.txt'
        path.write_bytes(b'origin')
        db.append_message('native-source', 'assistant', 'MEDIA:' + str(path))
        http = client(shelf)
        selected = http.get('/sources/sessions/native-source/artifacts').json()['items'][0]
        response = http.post('/sources/register-many', json={'title':'Wrong origin', 'session_id':'native-source',
                     'selections':[{'file':selected['file'],'source':selected['source'],'session_id':'unvalidated-session'}]})
        assert response.status_code == 422, response.text
        assert shelf.search()['total'] == 0
    finally:
        db.close()
