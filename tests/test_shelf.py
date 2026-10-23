"""Deterministic tests. All state is fictional and removed by TemporaryDirectory."""
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
HERMES = Path(os.environ.get("HERMES_SOURCE", Path.home() / ".hermes/hermes-agent"))
sys.path.insert(0, str(HERMES))
from hermes_constants import set_hermes_home_override, reset_hermes_home_override


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


api = load("shelf_test_api", ROOT / "dashboard/plugin_api.py")
plugin = load("shelf_test_plugin", ROOT / "__init__.py")


class ShelfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ds-", dir=os.environ.get("TMPDIR"))
        self.home = Path(self.tmp.name) / "home"
        self.workspace = self.home / "workspaces"
        self.workspace.mkdir(parents=True)
        self.token = set_hermes_home_override(self.home)
        self.store = api.Store(self.home)
        app = FastAPI()
        app.include_router(api.router, prefix="/api/plugins/delivery-shelf")
        self.client = TestClient(app)
        self.base = "/api/plugins/delivery-shelf"

    def tearDown(self):
        self.client.close()
        reset_hermes_home_override(self.token)
        self.tmp.cleanup()

    def create(self, **values):
        return self.store.create(api.EntryInput(title="A report", **values))

    def file(self, name="report.md", content=b"# Finished work\n<script>alert(1)</script>"):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return api.FileRef(root="workspaces", path=name)

    def test_crud_readback_revision_and_metadata_only_delete(self):
        ref = self.file()
        created = self.create(file=ref, tags=["Done", "done"], project="North")
        self.assertEqual(created["tags"], ["done"])
        edit = api.EntryUpdate.model_validate({**{k:v for k,v in created.items() if k not in ("id","created","updated")}, "title":"Changed"})
        updated = self.store.update(created["id"], edit)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(self.store.get(created["id"])["title"], "Changed")
        with self.assertRaises(HTTPException) as err: self.store.update(created["id"], edit)
        self.assertEqual(err.exception.status_code, 409)
        with self.assertRaises(HTTPException): self.store.delete(created["id"], 1)
        self.store.delete(created["id"], 2)
        self.assertTrue((self.workspace / ref.path).exists())
        self.assertEqual(self.store.search()["total"], 0)

    def test_search_exact_filters_literal_sql_and_paging(self):
        self.create(description="Unique 100% _ ' string", tags=["green"], project="North", kind="report")
        for n in range(3): self.create(project="Other")
        self.assertEqual(self.store.search(q="100% _ '", tag="GREEN", project="North", kind="report")["total"], 1)
        self.assertEqual(self.store.search(q="' OR 1=1 --")["total"], 0)
        self.assertEqual(self.store.search(tag="gree")["total"], 0)
        result=self.store.search(limit=2,offset=2)
        self.assertEqual((result["total"],len(result["items"])),(4,2))

    def test_http_crud_and_validation(self):
        response=self.client.post(self.base+"/entries",json={"title":"HTTP"})
        self.assertEqual(response.status_code,201,response.text)
        item=response.json()
        self.assertEqual(self.client.get(self.base+"/entries/"+item["id"]).json(),item)
        for payload in ({"title":" "},{"title":"a","unknown":1},{"title":"x","tags":["a"*41]},{"title":1},{"title":"x","file":{"root":"x","path":"/etc/passwd"}}):
            self.assertEqual(self.client.post(self.base+"/entries",json=payload).status_code,422)
        self.assertEqual(self.client.get(self.base+"/entries?limit=1000").status_code,422)
        self.assertEqual(self.client.delete(self.base+"/entries/"+item["id"]+"?revision=1").status_code,200)
        self.assertEqual(self.client.get(self.base+"/entries/"+item["id"]).status_code,404)

    def test_revision_bounds_and_strict_types(self):
        item = self.client.post(self.base + '/entries', json={'title': 'Bounds'}).json()
        url = self.base + '/entries/' + item['id']
        maximum = 9007199254740991
        for revision in (0, -1, maximum + 1, 9223372036854775808, 10**100, True, 1.5, '1', None):
            with self.subTest(revision=revision):
                with self.assertRaises(ValidationError):
                    api.EntryUpdate(title='Changed', revision=revision)
                self.assertEqual(self.client.put(url, json={'title': 'Changed', 'revision': revision}).status_code, 422)
                self.assertEqual(self.client.get(url).json(), item)
        for revision in ('0', '-1', str(maximum + 1), '9223372036854775808', str(10**100), 'true', '1.5', '1.0', '1e0', 'nope'):
            with self.subTest(query=revision):
                self.assertEqual(self.client.delete(url, params={'revision': revision}).status_code, 422)
                self.assertEqual(self.client.get(url).json(), item)
        self.assertEqual(api.EntryUpdate(title='Bounds', revision=maximum).revision, maximum)
        self.assertEqual(self.client.put(url, json={'title': 'Changed', 'revision': maximum}).status_code, 409)
        self.assertEqual(self.client.delete(url, params={'revision': maximum}).status_code, 409)
        self.assertEqual(self.client.get(url).json(), item)
        updated = self.client.put(url, json={'title': 'Changed', 'revision': 1})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['revision'], 2)
        self.assertEqual(self.client.delete(url, params={'revision': 2}).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_profile_hint_refused(self):
        self.assertEqual(self.client.get(self.base+"/status?profile=other").status_code,409)
        self.assertEqual(self.client.get(self.base+"/status?profile=default").status_code,200)
        self.assertEqual(self.client.post(self.base+"/entries?profile=other",json={"title":"foreign"}).status_code,409)
        self.assertEqual(self.store.search()["total"],0)

    def test_profile_isolation_concurrent(self):
        def run(label):
            home=Path(self.tmp.name)/"profiles"/label
            token=set_hermes_home_override(home)
            try:
                store=api.Store(api.bound_home())
                store.create(api.EntryInput(title=label))
                return api.profile_name(store.home),store.search()["items"][0]["title"]
            finally: reset_hermes_home_override(token)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(run,["alpha","beta"])),[("alpha","alpha"),("beta","beta")])
        self.assertEqual(self.store.search()["total"],0)

    def test_deny_traversal_hidden_sensitive_and_active_types(self):
        names=["../a.txt","/a.txt","a/../b.txt","a//b.txt","a\\b.txt",".env",".git/file.txt","id_rsa.txt","tokens.csv","private/report.pdf","credentials.json","secret.txt","auth.txt","config.txt","db.sqlite3","foo.html","foo.svg","foo.js","x:ads.txt","a\x00.txt"]
        for name in names:
            with self.subTest(name=name),self.assertRaises(ValidationError): api.FileRef(root="workspaces",path=name)

    def test_symlink_file_and_directory_denied(self):
        ref=self.file()
        (self.workspace/"link.md").symlink_to(self.workspace/ref.path)
        (self.workspace/"linked").symlink_to(self.workspace,target_is_directory=True)
        for path in ["link.md","linked/report.md"]:
            with self.subTest(path=path),self.assertRaises(HTTPException):
                api.open_file(self.home,api.FileRef(root="workspaces",path=path))

    def test_root_ancestor_symlink_and_hardlink_denied(self):
        ref=self.file()
        link=Path(self.tmp.name)/"root-link"
        link.symlink_to(self.workspace,target_is_directory=True)
        (api.data_dir(self.home)/"allowed-roots.json").write_text(json.dumps({"linked":str(link)}))
        with self.assertRaises(HTTPException):api.open_file(self.home,api.FileRef(root="linked",path=ref.path))
        (api.data_dir(self.home)/"allowed-roots.json").unlink()
        os.link(self.workspace/ref.path,self.workspace/"second.md")
        with self.assertRaises(HTTPException):api.open_file(self.home,ref)

    def test_descriptor_remains_pinned_after_path_replaced(self):
        ref=self.file(content=b"safe")
        with api.open_file(self.home,ref) as stream:
            (self.workspace/ref.path).rename(self.workspace/"old.md")
            (self.workspace/ref.path).symlink_to(self.workspace/"old.md")
            self.assertEqual(stream.read(),b"safe")
        with self.assertRaises(HTTPException):api.open_file(self.home,ref)

    def test_file_access_unsupported_platform_fails_closed(self):
        ref=self.file()
        with patch.object(os,"supports_dir_fd",set()):
            with self.assertRaises(HTTPException) as err:api.open_file(self.home,ref)
        self.assertEqual(err.exception.status_code,501)
        self.create()

    def test_policy_invalid_missing_alias_empty_and_revocation(self):
        ref=self.file()
        entry=self.create(file=ref)
        policy=api.data_dir(self.home)/"allowed-roots.json"
        policy.write_text("{}")
        self.assertEqual(self.client.get(self.base+f"/entries/{entry['id']}/file").status_code,403)
        for text in ["not json","[]",'{"x":"/"}', '{"x":"relative"}']:
            policy.write_text(text)
            with self.assertRaises(HTTPException) as err:api.allowed_roots(self.home)
            self.assertEqual(err.exception.status_code,503)

    def test_present_invalid_policy_never_falls_back_to_defaults(self):
        ref = self.file()
        entry = self.create(file=ref)
        policy = api.data_dir(self.home) / "allowed-roots.json"
        download = self.base + f"/entries/{entry['id']}/file"
        payload = {"title": "New delivery", "file": ref.model_dump()}
        self.assertEqual(self.client.get(download).status_code, 200)
        target = self.home / "operator-policy.json"
        target.write_text("{}")
        for state in ("linked", "dangling", "directory", "fifo"):
            with self.subTest(state=state):
                if state == "linked": policy.symlink_to(target)
                elif state == "dangling": policy.symlink_to(self.home / "absent-policy.json")
                elif state == "directory": policy.mkdir()
                else: os.mkfifo(policy)
                try:
                    self.assertEqual(self.client.get(download).status_code, 503)
                    self.assertEqual(self.client.post(self.base + "/entries", json=payload).status_code, 503)
                    self.assertEqual(self.store.search()["total"], 1)
                finally:
                    if state == "directory": policy.rmdir()
                    else: policy.unlink()
        # True absence restores the documented defaults; an explicit empty policy does not.
        self.assertEqual(self.client.get(download).status_code, 200)
        policy.write_text("{}")
        self.assertEqual(self.client.get(download).status_code, 403)

    def test_binary_download_text_preview_no_active_rendering(self):
        entry=self.create(file=self.file())
        path=self.base+f"/entries/{entry['id']}/file"
        response=self.client.get(path+"?preview=true")
        self.assertEqual(response.status_code,200)
        self.assertIn('<script>',response.json()["text"])
        self.assertTrue(response.headers['content-type'].startswith('application/json'))
        self.assertEqual(response.headers['cache-control'],'no-store')
        response=self.client.get(path)
        self.assertEqual(base64.b64decode(response.json()['base64']),(self.workspace/'report.md').read_bytes())
        self.assertEqual(response.json()['media_type'],'application/octet-stream')
        image=self.create(file=self.file('image.png',b'fictional fixture'))
        self.assertEqual(self.client.get(self.base+f"/entries/{image['id']}/file?preview=true").status_code,415)

    def test_preview_truncation_and_file_size_limit(self):
        entry=self.create(file=self.file(content=b'x'*70000))
        preview=self.client.get(self.base+f"/entries/{entry['id']}/file?preview=true").json()
        self.assertEqual(len(preview['text']),65536)
        self.assertTrue(preview['truncated'])
        with (self.workspace/'report.md').open('wb') as stream: stream.truncate(api.MAX_FILE+1)
        self.assertEqual(self.client.get(self.base+f"/entries/{entry['id']}/file").status_code,413)

    def test_deleted_file_metadata_still_editable(self):
        entry=self.create(file=self.file())
        (self.workspace/'report.md').unlink()
        update=api.EntryUpdate(title='still useful',file=entry['file'],revision=1)
        self.assertEqual(self.store.update(entry['id'],update)['title'],'still useful')

    def test_native_registration_and_tool_validation(self):
        class Context:
            def __init__(self):self.tools={};self.commands={}
            def register_tool(self,**kwargs):self.tools[kwargs['name']]=kwargs
            def register_command(self,name,handler,**kwargs):self.commands[name]=(handler,kwargs)
        ctx=Context();plugin.register(ctx)
        self.assertEqual(set(ctx.tools),{'delivery_shelf_register','delivery_shelf_search'})
        self.assertEqual(ctx.commands['shelf'][1]['argument_mode'],'text')
        result=json.loads(ctx.tools['delivery_shelf_register']['handler']({'title':'Tool delivery'}))
        self.assertTrue(result['ok'])
        self.assertIn('Tool delivery',ctx.commands['shelf'][0]('Tool'))
        for args in ({'limit':False},{'profile':'other'},{'q':1},{'offset':-1}):
            self.assertFalse(json.loads(ctx.tools['delivery_shelf_search']['handler'](args))['ok'])

    def test_concurrent_cold_service_import(self):
        fresh=load('cold_shelf_plugin',ROOT/'__init__.py')
        original=importlib.util.module_from_spec
        import time
        def delayed(spec):time.sleep(.02);return original(spec)
        with patch.object(importlib.util,'module_from_spec',delayed),ThreadPoolExecutor(max_workers=6) as pool:
            modules=list(pool.map(lambda _:fresh._service(),range(6)))
        self.assertEqual(len({id(m) for m in modules}),1)
        self.assertTrue(all(hasattr(m,'router') for m in modules))

    def test_session_reference_validation_and_native_fallback(self):
        item=json.loads(plugin._run('register',{'title':'Reference','session_id':'fictional-session_01'}))
        self.assertEqual(item['data']['session_id'],'fictional-session_01')
        for value in ('../foreign','x'*161,'bad\nvalue'):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                api.EntryInput(title='Reference',session_id=value)
        class Context:
            def register_tool(self,**kwargs):
                if kwargs['name']=='delivery_shelf_register':self.add=kwargs['handler']
            def register_command(self,*args,**kwargs):pass
        ctx=Context();plugin.register(ctx)
        item=json.loads(ctx.add({'title':'Implicit'},session_id='runtime-session'))
        self.assertEqual(item['data']['session_id'],'runtime-session')
        item=json.loads(ctx.add({'title':'Explicit','session_id':'chosen-session'},session_id='runtime-session'))
        self.assertEqual(item['data']['session_id'],'chosen-session')

    def test_http_home_rebound_between_requests(self):
        self.client.post(self.base+'/entries',json={'title':'Default-only'})
        other=Path(self.tmp.name)/'profiles'/'other'
        token=set_hermes_home_override(other)
        try:
            response=self.client.get(self.base+'/entries?profile=other')
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['total'],0)
            self.assertEqual(self.client.get(self.base+'/status?profile=default').status_code,409)
            self.client.post(self.base+'/entries?profile=other',json={'title':'Other-only'})
        finally:reset_hermes_home_override(token)
        self.assertEqual(self.client.get(self.base+'/entries').json()['items'][0]['title'],'Default-only')
        self.assertEqual(self.client.get(self.base+'/entries').json()['total'],1)

    def test_parallel_writes_and_private_permissions(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            items=list(pool.map(lambda n:self.store.create(api.EntryInput(title=str(n))),range(20)))
        self.assertEqual(len({i['id'] for i in items}),20)
        self.assertEqual(self.store.search()['total'],20)
        self.assertEqual(self.store.path.stat().st_mode & 0o777,0o600)
        with self.store.connect() as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')


if __name__=='__main__':unittest.main(verbosity=2)
