"""Bounded real document thumbnail and cache endpoint regressions."""
import base64
from io import BytesIO
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from hermes_state import SessionDB
from PIL import Image

from zipfile import ZipFile

from document_fixtures import pdf_bytes, docx_bytes
import test_desktop_sources as fixtures

api = fixtures.api


class DocumentThumbnails(unittest.TestCase):
    home: Path
    file: Path
    db: SessionDB
    client: TestClient
    setUp = fixtures.DesktopSources.setUp

    def selection(self, name='report.pdf', content=None):
        path = self.home/'workspaces'/name
        path.write_bytes(content if content is not None else pdf_bytes())
        self.db.append_message('fictional', 'assistant', 'MEDIA:'+str(path))
        item = next(item for item in self.client.get('/sources/sessions/fictional/artifacts').json()['items'] if item['name']==name)
        return path, {key:item[key] for key in ('source', 'file')}

    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('prlimit'), 'Poppler + prlimit required')
    def test_real_pdf_first_page_is_bounded_png_and_cache_survives_renderer_loss(self):
        _, selection = self.selection()
        result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 200, result.text)
        content = base64.b64decode(result.json()['base64'])
        self.assertEqual(result.json()['media_type'], 'image/png')
        with Image.open(BytesIO(content)) as image:
            self.assertLessEqual(max(image.size), 384)
            self.assertGreater(len(image.convert('RGB').getcolors(384*384) or []), 2)
        cached = list((self.home/'plugin-data/delivery-shelf/thumbnail-cache').glob('*.png'))
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0].read_bytes(), content)
        module = api.source_module('document_previews')
        with patch.object(module.shutil, 'which', return_value=None):
            again = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json(), result.json())
        self.assertEqual(self.client.get('/entries').json()['total'], 0)


    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('prlimit'), 'Poppler + prlimit required')
    def test_managed_pdf_cache_never_bypasses_integrity_or_origin_authorization(self):
        path, selection = self.selection()
        saved = self.client.post('/sources/register', json={'title':'PDF', 'session_id':'fictional', **selection}).json()
        url = '/entries/'+saved['id']+'/thumbnail'
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200, first.text)
        path.unlink()
        self.assertEqual(self.client.get(url).json(), first.json())
        # A cached thumbnail must not authorize a corrupted managed object.
        version = saved['versions'][0]
        stored = self.home/'plugin-data/delivery-shelf/managed-files'/version['id']/version['files'][0]['id']
        stored.chmod(0o600)
        stored.write_bytes(b'corrupt')
        self.assertEqual(self.client.get(url).status_code, 409)
        path.write_bytes(pdf_bytes())
        for request, status in [({'session_id':'foreign', **selection}, 404),
                ({'session_id':'fictional', **selection, 'source':{**selection['source'], 'digest':'0'*64}}, 409)]:
            result = self.client.post('/sources/thumbnail', json=request)
            self.assertEqual(result.status_code, status, result.text)

    def test_no_embedded_preview_malformed_documents_and_zip_fail_to_type_icon(self):
        for name, data in [('letter.docx', docx_bytes()), ('bad.docx', b'PK not a package'),
                ('bad.pdf', b'%PDF-1.4 invalid'), ('bundle.zip', docx_bytes())]:
            with self.subTest(name=name):
                _, selection = self.selection(name, data)
                result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
                self.assertEqual(result.status_code, 415, result.text)
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('prlimit'), 'Poppler + prlimit required')
    def test_cache_corruption_is_regenerated_and_eviction_is_bounded(self):
        _, selection = self.selection()
        result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 200, result.text)
        folder = self.home/'plugin-data/delivery-shelf/thumbnail-cache'
        cached = next(folder.glob('*.png'))
        cached.write_bytes(b'broken')
        module = api.source_module('document_previews')
        with patch.object(module, 'CACHE_ITEMS', 2):
            repaired = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
            self.assertEqual(repaired.json(), result.json())
            for name in ('Different page', 'Third page'):
                _, next_selection = self.selection('report.pdf', pdf_bytes(name))
                preview = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **next_selection})
                self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(len(list(folder.glob('*.png'))), 2)
        self.assertFalse(cached.exists())

    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('prlimit'), 'Poppler + prlimit required')
    def test_source_change_and_profile_switch_during_real_render_are_rejected(self):
        module = api.source_module('document_previews')
        real_render = module.pdf_page
        path, selection = self.selection()
        def replace_source(content, directory):
            result = real_render(content, directory)
            path.write_bytes(pdf_bytes('Replacement page'))
            return result
        with patch.object(module, 'pdf_page', side_effect=replace_source):
            result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 409, result.text)
        # A fresh input avoids the previous content-addressed cached page.
        path, selection = self.selection('other.pdf', pdf_bytes('Other document'))
        with patch.object(api, 'bound_home', return_value=self.home) as home:
            def switch_profile(content, directory):
                result = real_render(content, directory)
                home.return_value = self.home/'different'
                return result
            with patch.object(module, 'pdf_page', side_effect=switch_profile):
                result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 409, result.text)

    def test_cache_parent_symlink_does_not_create_a_directory_outside_profile(self):
        module = api.source_module('document_previews')
        target = self.home/'outside'
        target.mkdir()
        linked = self.home/'linked'
        linked.symlink_to(target, target_is_directory=True)
        with self.assertRaises(OSError):
            with module.cache_root(linked/'thumbnail-cache'):
                self.fail('Linked parent was admitted')
        self.assertEqual(list(target.iterdir()), [])

    def test_cache_symlink_never_reads_or_writes_its_target(self):
        _, selection = self.selection()
        target = self.home/'unrelated'
        target.mkdir()
        marker = target/'keep'
        marker.write_bytes(b'untouched')
        folder = self.home/'plugin-data/delivery-shelf/thumbnail-cache'
        folder.symlink_to(target, target_is_directory=True)
        result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 415, result.text)
        self.assertEqual(list(target.iterdir()), [marker])
        self.assertEqual(marker.read_bytes(), b'untouched')

    def test_oversize_office_registration_and_macro_extensions_stay_denied(self):
        oversized = self.home/'workspaces'/'large.docx'
        with oversized.open('wb') as output:
            output.truncate(api.MAX_FILE + 1)
        result = self.client.post('/entries', json={'title':'Too large', 'file':{'root':'workspaces','path':oversized.name}})
        self.assertEqual(result.status_code, 413, result.text)
        for name in ('macro.docm', 'legacy.doc', 'unsafe.html', 'hidden/../report.docx', 'secret.docx'):
            result = self.client.post('/entries', json={'title':'Denied', 'file':{'root':'workspaces','path':name}})
            self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    def test_broken_office_deflate_stream_fails_to_icon_not_server_error(self):
        from zipfile import ZIP_DEFLATED
        image = BytesIO()
        Image.new('RGB', (10, 10), 'white').save(image, format='PNG')
        package = BytesIO(docx_bytes())
        with ZipFile(package, 'a', compression=ZIP_DEFLATED) as archive:
            archive.writestr('docProps/thumbnail.png', image.getvalue())
            info = archive.getinfo('docProps/thumbnail.png')
        data = bytearray(package.getvalue())
        start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data[start:start+info.compress_size] = b'\xff' * info.compress_size
        _, selection = self.selection('broken.docx', bytes(data))
        with TestClient(self.client.app, raise_server_exceptions=False) as client:
            result = client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 415, result.text)

    def test_office_oversized_raster_header_fails_to_icon_not_server_error(self):
        import struct
        import zlib
        def chunk(kind, data):
            return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
        huge = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 100000, 100000, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(b'\0'))+chunk(b'IEND', b'')
        package = BytesIO(docx_bytes())
        with ZipFile(package, 'a') as archive:
            archive.writestr('docProps/thumbnail.png', huge)
        _, selection = self.selection('huge.docx', package.getvalue())
        result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 415, result.text)

    @unittest.skipUnless(shutil.which('pdftoppm') and shutil.which('prlimit'), 'Poppler + prlimit required')
    def test_office_embedded_real_page_thumbnail_without_office_execution(self):
        # The package stores a real preview of its matching document text. This
        # tests embedded previews, not a fake source->Office layout conversion.
        _, pdf_selection = self.selection()
        page = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **pdf_selection})
        self.assertEqual(page.status_code, 200, page.text)
        png = base64.b64decode(page.json()['base64'])
        package = BytesIO(docx_bytes())
        with ZipFile(package, 'a') as archive:
            archive.writestr('docProps/thumbnail.png', png)
        path, selection = self.selection('letter.docx', package.getvalue())
        module = api.source_module('document_previews')
        with patch.object(module.subprocess, 'run', side_effect=AssertionError('Office must never execute a converter')):
            result = self.client.post('/sources/thumbnail', json={'session_id':'fictional', **selection})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(base64.b64decode(result.json()['base64']), png)
        saved_response = self.client.post('/sources/register', json={
            'title':'Exact Office metadata', 'description':'Unchanged.', 'tags':['Word'],
            'session_id':'fictional', **selection})
        self.assertEqual(saved_response.status_code, 201, saved_response.text)
        saved = saved_response.json()
        path.unlink()
        result = self.client.get('/entries/'+saved['id']+'/thumbnail')
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(base64.b64decode(result.json()['base64']), png)
        self.assertEqual(self.client.get('/entries/'+saved['id']).json(), saved)


if __name__ == '__main__':
    unittest.main()
