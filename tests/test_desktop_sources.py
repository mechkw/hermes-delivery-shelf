"""File chooser and explicit draft generation through authenticated API seam."""
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_state import SessionDB

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desktop_source_api', ROOT/'dashboard/plugin_api.py')
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)

class DesktopSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home/'workspaces').mkdir()
        self.file = self.home/'workspaces/field-notes.md'
        self.file.write_text('Fictional meadow survey: three swallows.')
        self.db = SessionDB(self.home/'state.db')
        self.addCleanup(self.db.close)
        self.db.create_session('fictional', source='desktop')
        self.db.set_session_title('fictional', 'Meadow survey')
        self.db.append_message('fictional','user','Prepare the meadow report')
        self.anchor = self.db.append_message('fictional','assistant','Here is the report.\nMEDIA:'+str(self.file))
        self.db.append_message('fictional','user','FUTURE PRIVATE QUESTION')
        self.db.append_message('fictional','assistant','FUTURE ANSWER')
        self.db.append_message('fictional','tool','MEDIA:'+str(self.home/'workspaces/tool.md'))
        self.db.create_session('foreign', source='desktop')
        with __import__('sqlite3').connect(self.home/'state.db') as conn:
            conn.execute("UPDATE sessions SET profile_name='other' WHERE id='foreign'")
        self.home_patch = patch.object(api,'bound_home',return_value=self.home)
        self.home_patch.start(); self.addCleanup(self.home_patch.stop)
        app=FastAPI(); app.include_router(api.router)
        self.client=TestClient(app); self.addCleanup(self.client.close)

    def test_chooser_returns_files_not_messages_and_does_not_write(self):
        before=self.client.get('/entries').json()['total']
        sessions=self.client.get('/sources/sessions').json()
        self.assertEqual([s['id'] for s in sessions['items']],['fictional'])
        result=self.client.get('/sources/sessions/fictional/artifacts')
        self.assertEqual(result.status_code,200,result.text)
        items=result.json()['items']
        self.assertEqual([i['name'] for i in items],['field-notes.md'])
        self.assertEqual(items[0]['source']['message_id'],self.anchor)
        self.assertNotIn('preview',items[0])
        self.assertEqual(self.client.get('/entries').json()['total'],before)
        self.assertEqual(self.client.get('/sources/sessions?profile=other').status_code,409)
        self.assertEqual(self.client.get('/sources/sessions/foreign/artifacts').status_code,404)

    def test_generation_reads_file_and_only_anchored_history_without_saving(self):
        selected=self.client.get('/sources/sessions/fictional/artifacts').json()['items'][0]
        calls=[]
        async def complete(**kw):
            calls.append(kw)
            return SimpleNamespace(parsed={'title':'Meadow report','description':'Three swallows recorded.','tags':['survey']})
        ctx=SimpleNamespace(llm=SimpleNamespace(acomplete_structured=complete),on_unload=lambda f:None)
        api.bind_generation(ctx)
        before=self.client.get('/entries').json()
        result=self.client.post('/generation/draft',json={'session_id':'fictional','source':selected['source']})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['context']['content_mode'],'text')
        wire=str(calls[0])
        self.assertIn('three swallows',wire)
        self.assertIn('Prepare the meadow report',wire)
        self.assertNotIn('FUTURE',wire)
        self.assertNotIn('tools',calls[0])
        self.assertEqual(self.client.get('/entries').json(),before)
        self.assertEqual(len(calls),1)
        saved=self.client.post('/sources/register',json={'title':'Reviewed title','file':selected['file'],'session_id':'fictional','source':selected['source']})
        self.assertEqual(saved.status_code,201,saved.text)
        entry=saved.json()
        self.assertEqual(self.client.get('/entries/'+entry['id']).json(),entry)
        self.db.delete_session('fictional')
        edited=self.client.put('/entries/'+entry['id'],json={k:v for k,v in entry.items() if k not in ('id','source','created','updated')}|{'title':'Kept after pruning'})
        self.assertEqual(edited.status_code,200,edited.text)
        self.assertEqual(edited.json()['source'],selected['source'])

    def test_generation_rejects_file_change_during_inference(self):
        selected=self.client.get('/sources/sessions/fictional/artifacts').json()['items'][0]
        async def complete(**kw):
            self.file.write_text('Changed during inference')
            return SimpleNamespace(parsed={'title':'Stale','description':'','tags':[]})
        api.bind_generation(SimpleNamespace(llm=SimpleNamespace(acomplete_structured=complete),on_unload=lambda f:None))
        result=self.client.post('/generation/draft',json={'session_id':'fictional','source':selected['source']})
        self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(self.client.get('/entries').json()['total'],0)

    def test_file_inputs_images_unsupported_utf8_bounds_and_strict_output(self):
        import base64
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=')
        calls=[]
        async def complete(**kw):
            calls.append(kw)
            return SimpleNamespace(parsed={'title':'File','description':'Fictional','tags':[]})
        api.bind_generation(SimpleNamespace(llm=SimpleNamespace(acomplete_structured=complete),on_unload=lambda f:None))
        for name,data,mode in [('picture.png',png,'image'),('bundle.zip',b'PK opaque','history-only'),('paper.pdf',b'%PDF opaque','history-only'),('broken.txt',b'\xff','history-only (not UTF-8)'),('long.md',b'x'*70000,'text')]:
            file=self.home/'workspaces'/name;file.write_bytes(data)
            self.db.append_message('fictional','user','Describe this file')
            self.db.append_message('fictional','assistant','MEDIA:'+str(file))
            selected=next(i for i in self.client.get('/sources/sessions/fictional/artifacts').json()['items'] if i['name']==name)
            result=self.client.post('/generation/draft',json={'session_id':'fictional','source':selected['source']})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['context']['content_mode'],mode)
            blocks=calls[-1]['input']
            if mode=='image': self.assertEqual(blocks[-1]['data'],png)
            if mode.startswith('history-only'): self.assertEqual(len(blocks),1)
            if name=='long.md': self.assertTrue(result.json()['context']['file_truncated'])
        async def invalid(**kw): return SimpleNamespace(parsed={'title':'No','description':'','tags':[],'file':'invented'})
        api.bind_generation(SimpleNamespace(llm=SimpleNamespace(acomplete_structured=invalid),on_unload=lambda f:None))
        self.assertEqual(self.client.post('/generation/draft',json={'session_id':'fictional','source':selected['source']}).status_code,502)
        self.assertEqual(self.client.get('/entries').json()['total'],0)

    def test_explicit_visible_references_policy_and_stale_source(self):
        history=api.source_module('native_history');artifacts=api.source_module('artifact_source')
        raw=str(self.file)
        for content in ['Plain prose '+raw,'```\nMEDIA:'+raw+'\n```','<think>\nMEDIA:'+raw+'\n</think>','\x00json:'+__import__('json').dumps([{'type':'reasoning','text':'MEDIA:'+raw}])]:
            self.assertEqual(artifacts.paths(history,content),[])
        self.assertEqual(artifacts.paths(history,'[Download]('+raw+')'),[raw])
        selected=self.client.get('/sources/sessions/fictional/artifacts').json()['items'][0]
        source=dict(selected['source'],digest='0'*64)
        self.assertEqual(self.client.post('/sources/register',json={'title':'No','file':selected['file'],'source':source,'session_id':'fictional'}).status_code,409)
        self.file.unlink();self.file.symlink_to(self.home/'state.db')
        self.assertEqual(self.client.get('/sources/sessions/fictional/artifacts').json()['items'],[])
        self.assertEqual(self.client.get('/entries').json()['total'],0)

    def test_native_compression_history_and_private_carriers(self):
        import json
        self.db.create_session('root','desktop')
        for i in range(12):
            self.db.append_message('root','user',f'User {i}')
            self.db.append_message('root','assistant',f'Answer {i}')
        history=self.db.get_messages_as_conversation('root')
        self.db.publish_compression_child(parent_session_id='root',child_session_id='tip',source='desktop',messages=history[-4:],require_compression_lease=False)
        self.db.append_message('tip','user',[{'type':'text','text':'Actual focal request'},{'type':'text','text':'<memory-context>\nPRIVATE memory\n</memory-context>\nPRIVATE plugin spill'}])
        self.db.append_message('tip','assistant','<think>PRIVATE reasoning</think>\nMEDIA:'+str(self.file))
        self.db.append_message('tip','user','FUTURE question')
        self.db.get_messages('tip')
        selected=self.client.get('/sources/sessions/tip/artifacts').json()['items'][0]
        calls=[]
        async def complete(**kw):
            calls.append(kw);return SimpleNamespace(parsed={'title':'File','description':'','tags':[]})
        api.bind_generation(SimpleNamespace(llm=SimpleNamespace(acomplete_structured=complete),on_unload=lambda f:None))
        self.client.put('/generation/settings',json={'previous_exchanges':5})
        with __import__('sqlite3').connect(self.home/'state.db') as db: before=list(db.iterdump())
        result=self.client.post('/generation/draft',json={'session_id':'tip','source':selected['source'],'previous_exchanges':5})
        self.assertEqual(result.status_code,200,result.text)
        wire=json.dumps(calls)
        self.assertNotIn('PRIVATE',wire);self.assertNotIn('FUTURE',wire)
        self.assertIn('Actual focal request',wire);self.assertIn('User 7',wire);self.assertNotIn('User 6',wire)
        self.assertEqual(result.json()['context']['previous_exchanges'],5)
        with __import__('sqlite3').connect(self.home/'state.db') as db: self.assertEqual(list(db.iterdump()),before)

    def test_settings_default_read_does_not_persist_and_explicit_presets_survive(self):
        self.assertEqual(self.client.get('/generation/settings').json(),{'previous_exchanges':10})
        with __import__('sqlite3').connect(self.home/'plugin-data/delivery-shelf/shelf.sqlite3') as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='settings'").fetchone())
        for value in (5,10,20,50):
            self.assertEqual(self.client.put('/generation/settings',json={'previous_exchanges':value}).status_code,200)
            self.assertEqual(self.client.get('/generation/settings').json()['previous_exchanges'],value)
        self.assertEqual(self.client.put('/generation/settings',json={'previous_exchanges':17}).status_code,422)

if __name__=='__main__': unittest.main()
