"""Real PDF/DOCX Add regressions using the host and PTB capture transport."""
import unittest
from document_fixtures import pdf_bytes, docx_bytes
from test_telegram_reported_regressions import ReportedTelegramRegressions


class DocumentDelivery(ReportedTelegramRegressions):
    # Inherited acceptance tests also guard owner/profile/session boundaries.
    async def test_standalone_pdf_and_docx_keep_explicit_metadata_and_saved_bytes(self):
        for name, content in [('solo.pdf', pdf_bytes()), ('solo.docx', docx_bytes())]:
            with self.subTest(name=name):
                path = self.home/'workspaces'/name
                path.write_bytes(content)
                self.db.append_message(self.session.session_id, 'assistant', 'MEDIA:'+str(path))
                saved = await self.quick_save(
                    'add Literal title #Office,Office --description " Exact description "',
                    'Saved to Delivery Shelf: Literal title')
                self.assertEqual(self.store.get(saved['id']), saved)
                self.assertEqual(saved['files'], [{'root':'workspaces', 'path':name}])
                self.assertEqual(saved['title'], 'Literal title')
                self.assertEqual(saved['description'], ' Exact description ')
                self.assertEqual(saved['tags'], ['Office', 'Office'])
                self.assertEqual(saved['session_id'], self.session.session_id)
                path.unlink()
                self.assertEqual(self.api.read_entry_file(self.store, saved)[1], content)
        self.assertEqual(self.model_calls, [])
        self.injection.assert_not_called()

    async def test_pdf_and_docx_in_same_answer_can_choose_and_save_exact_documents(self):
        documents = {'report.pdf': pdf_bytes(), 'letter.docx': docx_bytes()}
        for name, content in documents.items():
            (self.home/'workspaces'/name).write_bytes(content)
        self.db.append_message(self.session.session_id, 'assistant', '\n'.join(
            'MEDIA:'+str(self.home/'workspaces'/name) for name in documents))
        await self.manual_add()
        self.assertTrue(set(documents).issubset({b['text'] for b in self.buttons()}))
        await self.click('report.pdf')
        saved = self.store.search()['items'][0]
        saved_pdf = saved
        self.assertEqual(saved['file']['path'], 'report.pdf')
        name, content, media_type = self.api.read_entry_file(self.store, saved)
        self.assertEqual((name, content, media_type), ('report.pdf', documents['report.pdf'], 'application/pdf'))
        await self.click('View saved file')
        await self.click('Add')
        await self.click('letter.docx')
        saved = self.store.search()['items'][0]
        self.assertEqual(saved['file']['path'], 'letter.docx')
        (self.home/'workspaces/report.pdf').unlink()
        (self.home/'workspaces/letter.docx').unlink()
        self.assertEqual(self.api.read_entry_file(self.store, saved_pdf)[1], documents['report.pdf'])
        name, content, media_type = self.api.read_entry_file(self.store, saved)
        self.assertEqual(name, 'letter.docx')
        self.assertEqual(content, documents['letter.docx'])
        self.assertEqual(media_type, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        self.assertEqual(self.store.search()['total'], 2)
        self.injection.assert_not_called()


if __name__ == '__main__':
    unittest.main()
