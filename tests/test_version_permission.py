"""Delivery-scoped read/revoke; no route can grant initial or standing consent."""
import sqlite3
from test_lifecycle_settings import api, shelf, client, saved


def test_delivery_permission_read_revoke_and_pause(shelf):
    item, other = saved(shelf), saved(shelf, 'other.txt')
    http = client(shelf)
    url = f"/entries/{item['id']}/version-permission"
    assert http.get(url).status_code == 200
    assert http.get(url).json() == {'always': False, 'paused': False}
    db = api.data_dir(shelf.home) / 'agent-links.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS version_permissions(entry_id TEXT NOT NULL, owner TEXT NOT NULL, PRIMARY KEY(entry_id,owner))')
        conn.executemany('INSERT INTO version_permissions VALUES (?,?)', [(item['id'],'cli'),(item['id'],'telegram'),(other['id'],'cli')])
    assert http.get(url).json() == {'always': True, 'paused': False}
    for action in ('archive', 'trash'):
        shelf.bulk_action({'action':action,'ids':[item['id']]})
        assert http.get(url).json() == {'always': True, 'paused': True}
        shelf.bulk_action({'action':'restore','ids':[item['id']]})
    before = shelf.get(item['id'])
    assert http.delete(url).json() == {'always': False, 'paused': False}
    assert http.get(url).json() == {'always': False, 'paused': False}
    assert http.get(f"/entries/{other['id']}/version-permission").json()['always'] is True
    assert shelf.get(item['id']) == before
    assert http.post(url, json={'always':True}).status_code == 405
    assert http.get('/entries/'+'a'*32+'/version-permission').status_code == 404
    assert http.delete('/entries/'+'a'*32+'/version-permission').status_code == 404
