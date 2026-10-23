"""Native host integration probe in a disposable home; never uses a live bank."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SOURCE = Path(os.environ.get('HERMES_SOURCE', Path.home()/'.hermes/hermes-agent'))
ROOT = Path(__file__).resolve().parents[1]


def prepare(home):
    home.mkdir(parents=True, exist_ok=True)
    package=home/'plugins/delivery-shelf'
    package.mkdir(parents=True)
    for filename in ('plugin.yaml','__init__.py'):
        shutil.copy2(ROOT/filename,package/filename)
    for folder in ('dashboard','desktop'):
        shutil.copytree(ROOT/folder,package/folder,ignore=shutil.ignore_patterns('__pycache__'))
    (home/'config.yaml').write_text('plugins:\n  enabled: [delivery-shelf]\n  isolation: in_process\n')
    (home/'workspaces').mkdir()
    (home/'workspaces/example.md').write_text('# Fictional test deliverable\n<script>window.evil=true</script>')
    return package


def host(home):
    os.environ['HERMES_HOME']=str(home)
    os.environ['HERMES_PROFILE']='default'
    os.environ['HOME']=str(home.parent/'account')
    os.environ['HERMES_DASHBOARD_SESSION_TOKEN']='fictional-test-session'
    os.environ['HERMES_DISABLE_TELEMETRY']='1'
    sys.path.insert(0,str(SOURCE))
    from hermes_cli import web_server
    from hermes_cli.web_server_dashboard import _mount_plugin_api_routes, mount_spa
    _mount_plugin_api_routes()
    # Native order: plugin routes BEFORE catch-all, exactly as start_dashboard.
    return web_server


def probe():
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory(prefix='dsn-',dir=os.environ.get('TMPDIR')) as directory:
        home=Path(directory)/'home'
        prepare(home)
        ws=host(home)
        from hermes_cli.web_server_dashboard import mount_spa
        mount_spa(ws.app)
        headers={'X-Hermes-Session-Token':'fictional-test-session'}
        # No lifespan: exercise native HTTP/mount/auth without starting schedulers,
        # reconciling session banks, or invoking the host's environment bootstrap.
        from contextlib import closing
        with closing(TestClient(ws.app,base_url='http://localhost')) as client:
            prefix='/api/plugins/delivery-shelf'
            r=client.get(prefix+'/status')
            assert r.status_code==401,(r.status_code,r.text)
            r=client.get(prefix+'/status',headers=headers)
            assert r.status_code==200,(r.status_code,r.text)
            assert r.json()['profile']=='default'
            r=client.post(prefix+'/entries',headers=headers,json={'title':'Native mount proof'})
            assert r.status_code==201,(r.status_code,r.text)
            entry=r.json()
            assert client.get(prefix+'/entries/'+entry['id'],headers=headers).json()['title']=='Native mount proof'
            assert client.get('/dashboard-plugins/delivery-shelf/plugin_api.py',headers=headers).status_code in (403,404)
            assert client.get('/dashboard-plugins/delivery-shelf/dist/index.js',headers=headers).status_code==200
            # Live effective policy gate must close an already-mounted router.
            (home/'config.yaml').write_text('plugins:\n  enabled: []\n  disabled: [delivery-shelf]\n  isolation: in_process\n')
            r=client.get(prefix+'/status',headers=headers)
            assert r.status_code==404,(r.status_code,r.text)
        print('NATIVE API: 401 unauthenticated; authenticated discovery/CRUD/readback 200/201; Python source denied; bundle served; disabled router 404.')


if __name__=='__main__':probe()
