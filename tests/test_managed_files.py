"""Focused native catalog durability contracts; no installed profile is touched."""
import importlib.util
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location('managed_files_contract_api', Path(__file__).parents[1] / 'dashboard/plugin_api.py')
assert SPEC is not None and SPEC.loader is not None
api = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = api
SPEC.loader.exec_module(api)


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    home = tmp_path / 'profile'
    (home / 'workspaces').mkdir(parents=True)
    monkeypatch.setattr(api, 'bound_home', lambda: home)
    return api.Store(home)


def source(shelf, name='report.txt', data=b'original bytes'):
    path = shelf.home / 'workspaces' / name
    path.write_bytes(data)
    return path, api.FileRef(root='workspaces', path=name)


def client(shelf):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.request_store] = lambda: shelf
    return TestClient(app)


def test_create_copies_bytes_before_success(shelf):
    path, ref = source(shelf)
    saved = shelf.create(api.EntryInput(title='Original', file=ref))
    path.unlink()
    assert api.read_entry_file(shelf, saved) == ('report.txt', b'original bytes', 'text/plain')
    version = saved['versions'][0]
    assert saved['current_version'] == version['id']
    assert version['number'] == 1
    assert version['files'][0]['size'] == len(b'original bytes')
    assert shelf.search()['items'][0] == saved
    assert client(shelf).get(f"/entries/{saved['id']}/file").status_code == 200


def test_versions_multiple_files_and_metadata_survive_deleted_sources(shelf):
    first, ref = source(shelf)
    second, other = source(shelf, 'chart.csv', b'x,y\n1,2')
    saved = shelf.create(api.EntryInput(title='  Literal title  ', tags=[' Tag ', 'Tag', 'Tag'],
                                      description=' exact\ntext ', files=[ref, other]))
    original = saved['versions'][0]
    first.unlink()
    second.unlink()
    updated = shelf.update(saved['id'], api.EntryUpdate(title=saved['title'], tags=saved['tags'],
                                                       description='new description', revision=1))
    assert updated['versions'] == saved['versions']
    assert updated['files'] == [ref.model_dump(), other.model_dump()]
    assert updated['title'] == '  Literal title  '
    assert updated['tags'] == [' Tag ', 'Tag', 'Tag']
    first.write_bytes(b'replacement bytes')
    response = client(shelf).post(f"/entries/{saved['id']}/versions",
        json={'revision': 2, 'files': [ref.model_dump()]})
    assert response.status_code == 201, response.text
    current = response.json()
    assert [v['number'] for v in current['versions']] == [1, 2]
    first.unlink()
    assert api.read_entry_file(shelf, current)[1] == b'replacement bytes'
    assert api.read_entry_file(shelf, current, original['id'], original['files'][1]['id'])[1] == b'x,y\n1,2'
    url = f"/entries/{saved['id']}/versions/{original['id']}/files/{original['files'][0]['id']}"
    assert client(shelf).get(url).json()['name'] == 'report.txt'
    assert client(shelf).post(f"/entries/{saved['id']}/versions", json={'revision': 2, 'files': [ref.model_dump()]}).status_code == 409


def test_register_once_copies_and_failed_authorization_saves_nothing(shelf, monkeypatch):
    path, ref = source(shelf)
    calls = []
    item, existing = shelf.register_file_once(api.EntryInput(title='One', file=ref), authorize_commit=lambda: calls.append(True))
    assert not existing and len(item['versions']) == 1
    item2, existing = shelf.register_file_once(api.EntryInput(title='Do not overwrite', file=ref), authorize_commit=lambda: calls.append(True))
    assert existing and item2 == item and calls == [True, True]
    path.unlink()
    assert api.read_entry_file(shelf, item)[1] == b'original bytes'
    _, another = source(shelf, 'other.txt')
    def deny():
        raise ValueError('expired')
    with pytest.raises(ValueError, match='expired'):
        shelf.create(api.EntryInput(title='Never saved', file=another), authorize_commit=deny)
    assert shelf.search()['total'] == 1
    with pytest.raises(ValueError, match='expired'):
        shelf.register_file_once(api.EntryInput(title='Never registered', file=another), authorize_commit=deny)
    assert shelf.search()['total'] == 1
    assert len(list(shelf.managed().directory.iterdir())) == 1
    managed = api.source_module('managed_files')
    def broken_sync(fd):
        raise OSError('disk failure')
    monkeypatch.setattr(managed.os, 'fsync', broken_sync)
    with pytest.raises(OSError, match='disk failure'):
        shelf.create(api.EntryInput(title='Failed copy', file=another))
    assert shelf.search()['total'] == 1
    assert len(list(shelf.managed().directory.iterdir())) == 1


def test_changed_reference_retains_original(shelf):
    old_path, old_ref = source(shelf)
    _, new_ref = source(shelf, 'second.txt', b'new')
    saved = shelf.create(api.EntryInput(title='Saved', file=old_ref))
    old_path.unlink()
    changed = shelf.update(saved['id'], api.EntryUpdate(title='Changed', file=new_ref, revision=1))
    assert len(changed['versions']) == 2
    assert api.read_entry_file(shelf, changed)[1] == b'new'
    assert api.read_entry_file(shelf, changed, saved['current_version'])[1] == b'original bytes'


def test_old_catalog_and_metadata_only_entries_are_readable(shelf):
    import json
    _, ref = source(shelf)
    payload = {'title': 'Legacy', 'description': '', 'tags': [], 'kind': 'document',
               'project': '', 'session_id': '', 'file': ref.model_dump()}
    with shelf.connect() as conn:
        conn.execute('INSERT INTO entries VALUES (?,?,?,?,?)', ('a' * 32, json.dumps(payload), 1, 2, 3))
    reopened = api.Store(shelf.home)
    legacy = reopened.get('a' * 32)
    assert legacy['revision'] == 3 and legacy['created'] == 1
    assert legacy['versions'] == [] and legacy['current_version'] is None
    assert api.read_entry_file(reopened, legacy)[1] == b'original bytes'
    plain = reopened.create(api.EntryInput(title='Metadata only'))
    assert plain['versions'] == []
    with pytest.raises(api.HTTPException) as error:
        api.read_entry_file(reopened, plain)
    assert error.value.status_code == 404


@pytest.fixture
def conversation(shelf):
    from hermes_state import SessionDB
    db = SessionDB(shelf.home / 'state.db')
    db.create_session('native-contract', source='desktop')
    paths = [source(shelf), source(shelf, 'appendix.md', b'appendix')]
    db.append_message('native-contract', 'user', 'Produce both files')
    db.append_message('native-contract', 'assistant', '\n'.join('MEDIA:' + str(path) for path, _ in paths))
    try:
        yield client(shelf).get('/sources/sessions/native-contract/artifacts').json()['items']
    finally:
        db.close()


def test_register_many_revalidates_every_exact_source_and_saves_one_delivery(shelf, conversation):
    selections = [{'file': item['file'], 'source': item['source']} for item in conversation]
    body = {'title': '  Supplied title  ', 'description': ' Text\nunchanged ',
            'tags': ['Exact', 'Exact'], 'session_id': 'native-contract', 'selections': selections}
    bad = {**body, 'selections': [selections[0], {**selections[1], 'source': {**selections[1]['source'], 'digest': '0' * 64}}]}
    assert client(shelf).post('/sources/register-many', json=bad).status_code == 409
    assert shelf.search()['total'] == 0
    saved_response = client(shelf).post('/sources/register-many', json=body)
    assert saved_response.status_code == 201, saved_response.text
    saved = saved_response.json()
    assert saved['title'] == body['title'] and saved['tags'] == body['tags']
    assert shelf.search()['total'] == 1
    assert len(saved['versions'][0]['files']) == 2
    assert saved['file'] == selections[0]['file']


def test_generation_only_requests_missing_fields_and_keeps_exact_supplied(shelf, conversation):
    from types import SimpleNamespace
    calls = []
    async def complete(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(parsed={'description': 'Generated from the file'})
    ctx = SimpleNamespace(llm=SimpleNamespace(acomplete_structured=complete), on_unload=lambda callback: None)
    api.bind_generation(ctx)
    supplied = {'title': '  literal title  ', 'tags': ['Exact', 'Exact', ' exact ']}
    response = client(shelf).post('/generation/draft', json={
        'session_id': 'native-contract', 'source': conversation[0]['source'],
        'requested_fields': ['title', 'description', 'tags'], 'supplied_metadata': supplied})
    assert response.status_code == 200, response.text
    assert response.json()['draft'] == {**supplied, 'description': 'Generated from the file'}
    assert calls[0]['json_schema']['required'] == ['description']
    assert set(calls[0]['json_schema']['properties']) == {'description'}
    assert shelf.search()['total'] == 0


def test_thumbnail_uses_copied_image_and_managed_corruption_never_falls_back(shelf):
    import base64
    image = b'\x89PNG\r\n\x1a\nopaque-test-image'
    path, ref = source(shelf, 'picture.png', image)
    saved = shelf.create(api.EntryInput(title='Picture', file=ref))
    path.unlink()
    response = client(shelf).get(f"/entries/{saved['id']}/thumbnail")
    assert response.status_code == 200, response.text
    assert base64.b64decode(response.json()['base64']) == image
    version = saved['versions'][0]
    managed = shelf.managed().directory / version['id'] / version['files'][0]['id']
    managed.unlink()
    path.write_bytes(b'not the saved bytes')
    with pytest.raises(api.HTTPException) as error:
        api.read_entry_file(shelf, saved)
    assert error.value.status_code == 503


def test_new_files_update_and_failed_version_are_atomic(shelf):
    path, ref = source(shelf)
    saved = shelf.create(api.EntryInput(title='Initial', file=ref))
    _, other = source(shelf, 'replacement.md', b'changed')
    updated = shelf.update(saved['id'], api.EntryUpdate(title='Updated', files=[other], revision=1))
    assert updated['file'] == other.model_dump()
    assert len(updated['versions']) == 2
    path.unlink()
    response = client(shelf).post(f"/entries/{saved['id']}/versions", json={
        'revision': 2, 'files': [other.model_dump(), ref.model_dump()]})
    assert response.status_code == 403
    assert shelf.get(saved['id']) == updated
    assert len(list(shelf.managed().directory.iterdir())) == 2


def test_version_file_ids_cannot_cross_entries(shelf):
    _, ref = source(shelf)
    one = shelf.create(api.EntryInput(title='One', file=ref))
    two = shelf.create(api.EntryInput(title='Two', file=ref))
    foreign_version = two['versions'][0]
    with pytest.raises(api.HTTPException) as error:
        api.read_entry_file(shelf, one, foreign_version['id'], foreign_version['files'][0]['id'])
    assert error.value.status_code == 404
