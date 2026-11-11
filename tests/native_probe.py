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
    for source in (ROOT/'plugin.yaml', *ROOT.glob('*.py')):
        shutil.copy2(source, package/source.name)
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
    # Import performs the native API mount before the SPA catch-all. Mounting
    # again can replace module identities while existing routes retain models.
    from hermes_cli import web_server
    return web_server


def probe():
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory(prefix='dsn-',dir=os.environ.get('TMPDIR')) as directory:
        home=Path(directory)/'home'
        prepare(home)
        ws=host(home)
        routes = [getattr(route, 'path', '') for route in ws.app.routes]
        catch_all = [i for i, route in enumerate(routes) if route == '/{full_path:path}']
        plugin_routes = [i for i, route in enumerate(routes) if route.startswith('/api/plugins/')]
        assert len(catch_all) == 1 and plugin_routes, routes
        assert max(plugin_routes) < catch_all[0], routes
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
            # Native loader registration → command dispatcher → public HTTP readback.
            from hermes_cli.plugins import get_plugin_command_handler
            from hermes_cli.plugin_command_dispatch import invoke_plugin_command
            handler = get_plugin_command_handler('shelf')
            assert callable(handler)
            reply = invoke_plugin_command(handler, 'add Slash proof #native, telegram --description "Fictional proof." --file workspaces:example.md',
                                          session_id='fictional-native-session', platform='telegram')
            assert 'Saved to Delivery Shelf: Slash proof' in reply, reply
            matches = client.get(prefix+'/entries?q=Slash%20proof',headers=headers).json()
            assert matches['total'] == 1, matches
            assert matches['items'][0]['tags'] == ['native', 'telegram']
            assert matches['items'][0]['session_id'] == 'fictional-native-session'
            # Native consent + routing boundary. The receiving gateway is a capture
            # double here: queued is deliberately NOT claimed as a completed save.
            from hermes_cli.plugins import get_plugin_manager
            manager = get_plugin_manager()
            owner, queued = object(), []
            def receive(**payload):
                queued.append(payload)
                return True
            manager.set_gateway_message_injector(owner, receive)
            try:
                args = 'add --file workspaces:example.md'
                context = {'session_id': 'fictional-native-session', 'session_key': 'telegram:fictional', 'platform': 'telegram'}
                denied = invoke_plugin_command(handler, args, **context)
                assert 'not saved' in denied and not queued, denied
                (home/'config.yaml').write_text('plugins:\n  enabled: [delivery-shelf]\n  isolation: in_process\n  entries:\n    delivery-shelf:\n      allow_gateway_injection: true\n')
                accepted = invoke_plugin_command(handler, args, **context)
                assert accepted is None and len(queued) == 1, (accepted, queued)
                assert queued[0]['session_key'] == 'telegram:fictional'
                assert Path(queued[0]['plugin_home']).resolve() == home.resolve()
                assert queued[0]['plugin_id'] == 'delivery-shelf'
                assert '"missing": ["title", "tags", "description"]' in queued[0]['content']
                assert client.get(prefix+'/entries',headers=headers).json()['total'] == 2
            finally:
                manager.clear_gateway_message_injector(owner)
            # Live effective policy gate must close an already-mounted router.
            (home/'config.yaml').write_text('plugins:\n  enabled: []\n  disabled: [delivery-shelf]\n  isolation: in_process\n')
            r=client.get(prefix+'/status',headers=headers)
            assert r.status_code==404,(r.status_code,r.text)
        print('NATIVE API: 401 unauthenticated; authenticated CRUD and native slash-command save/readback; Python source denied; bundle served; disabled router 404.')


if __name__=='__main__':probe()
