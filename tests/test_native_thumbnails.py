"""Real source-origin and managed-file thumbnail endpoint regressions."""
import base64
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from hermes_state import SessionDB

import test_desktop_sources as fixtures

api = fixtures.api
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=')


class NativeThumbnails(unittest.TestCase):
    home: Path
    file: Path
    client: TestClient
    db: SessionDB
    setUp = fixtures.DesktopSources.setUp

    def image_selection(self):
        image = self.home / 'workspaces' / 'cover.png'
        image.write_bytes(PNG)
        self.db.append_message('fictional', 'assistant', 'MEDIA:' + str(image))
        items = self.client.get('/sources/sessions/fictional/artifacts').json()['items']
        selected = next(item for item in items if item['name'] == 'cover.png')
        return image, {key: selected[key] for key in ('file', 'source')}

    def test_source_image_preview_uses_selected_origin_without_saving(self):
        _, selection = self.image_selection()
        result = self.client.post('/sources/thumbnail', json={'session_id': 'fictional', **selection})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {'base64': base64.b64encode(PNG).decode(), 'media_type': 'image/png'})
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    def test_gallery_can_preview_second_saved_file_after_source_deletion(self):
        image, selection = self.image_selection()
        saved = self.client.post('/entries', json={'title': 'Mixed delivery', 'files': [
            {'root': 'workspaces', 'path': self.file.name}, selection['file']]}).json()
        version = saved['versions'][0]
        file_id = version['files'][1]['id']
        image.unlink()
        result = self.client.get(f"/entries/{saved['id']}/thumbnail", params={
            'version_id': version['id'], 'file_id': file_id})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(base64.b64decode(result.json()['base64']), PNG)

    def test_source_preview_rejects_foreign_and_stale_origin(self):
        _, selection = self.image_selection()
        foreign = self.client.post('/sources/thumbnail', json={'session_id': 'foreign', **selection})
        self.assertEqual(foreign.status_code, 404, foreign.text)
        changed = {**selection, 'source': {**selection['source'], 'digest': '0' * 64}}
        stale = self.client.post('/sources/thumbnail', json={'session_id': 'fictional', **changed})
        self.assertEqual(stale.status_code, 409, stale.text)


if __name__ == '__main__':
    unittest.main()
