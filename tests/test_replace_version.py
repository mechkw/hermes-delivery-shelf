"""Replacing one delivered file must retain the saved companion bytes."""
from test_lifecycle_settings import api, shelf, client


def test_replace_one_file_keeps_companion_without_original(shelf):
    folder = shelf.home / 'workspaces'
    (folder/'first.txt').write_bytes(b'first v1')
    (folder/'companion.txt').write_bytes(b'companion v1')
    first = {'root':'workspaces','path':'first.txt'}
    companion = {'root':'workspaces','path':'companion.txt'}
    saved = shelf.create(api.EntryInput(title='Pair', files=[first, companion], session_id='source-chat'))
    original = saved['versions'][0]
    (folder/'first.txt').unlink()
    (folder/'companion.txt').unlink()
    (folder/'revised.txt').write_bytes(b'first v2')
    response = client(shelf).post(f"/entries/{saved['id']}/versions", json={
        'revision':1, 'files':[{'root':'workspaces','path':'revised.txt'}],
        'replace_file':first, 'session_id':'revision-chat'})
    assert response.status_code == 201, response.text
    updated = response.json()
    assert updated['files'] == [{'root':'workspaces','path':'revised.txt'}, companion]
    version = updated['versions'][1]
    assert api.read_entry_file(shelf,updated,version['id'],version['files'][0]['id'])[1] == b'first v2'
    assert api.read_entry_file(shelf,updated,version['id'],version['files'][1]['id'])[1] == b'companion v1'
    assert version['files'][1]['provenance'] == original['files'][1]['provenance']
    assert version['files'][0]['provenance']['session_id'] == 'revision-chat'
    assert version['provenance']['session_id'] is None
    assert updated['versions'][0] == original
    assert not (folder/'companion.txt').exists()
