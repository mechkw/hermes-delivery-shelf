"""Saved integration fixture: native auth/router, fictional homes, no lifespan."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from native_probe import host, ROOT

IDS = ('conversation-bookmarks', 'delivery-shelf')
scenario = sys.argv[3]
frontend_mode, scenario = scenario.split('--', 1) if '--' in scenario else ('matched', scenario)
peer = Path(os.environ.get('SAVED_PEER_REPO', ROOT.parent / ('hermes-delivery-shelf' if ROOT.name.endswith('bookmarks') else 'hermes-conversation-bookmarks')))
repos = {ROOT.name.removeprefix('hermes-'): ROOT, peer.name.removeprefix('hermes-'): peer}
installed = list(IDS)
if scenario.endswith('-only'):
    installed = [scenario.removesuffix('-only')]
disabled: list[str] = list(IDS) if scenario == 'both-disabled' else ([scenario.removesuffix('-disabled')] if scenario.endswith('-disabled') else [])
enabled = [name for name in installed if name not in disabled]
frontend = list(IDS) if frontend_mode == 'ui-both' else (['conversation-bookmarks'] if frontend_mode == 'ui-bookmarks' else ['delivery-shelf'] if frontend_mode == 'ui-shelf' else list(enabled))
with tempfile.TemporaryDirectory(prefix='sv-', dir=sys.argv[2]) as directory:
    home = Path(directory) / 'home'
    home.mkdir()
    for name in installed:
        target = home / 'plugins' / name
        target.mkdir(parents=True)
        for file in ('__init__.py', 'plugin.yaml', 'telegram_shelf.py'):
            if (repos[name] / file).is_file():
                shutil.copy2(repos[name] / file, target / file)
        for folder in ('dashboard', 'desktop'):
            shutil.copytree(repos[name] / folder, target / folder, ignore=shutil.ignore_patterns('__pycache__'))
    (home / 'config.yaml').write_text('plugins:\n  isolation: in_process\n  enabled: '+json.dumps(enabled)+'\n  disabled: '+json.dumps(disabled)+'\n')
    (home / 'workspaces').mkdir()
    (home / 'workspaces' / 'example.md').write_text('Fictional Saved delivery.\n')
    with closing(sqlite3.connect(home / 'state.db')) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, profile_name TEXT)')
        db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT)')
        db.execute("INSERT INTO sessions VALUES ('fictional-session-01','default')")
        db.execute("INSERT INTO messages VALUES (1,'fictional-session-01')")
        db.commit()
    ws = host(home)
    from fastapi.responses import FileResponse, HTMLResponse
    import uvicorn
    qa = Path(sys.argv[2])

    @ws.app.get('/qa/{adapter}')
    def page(adapter: str):
        if adapter not in ('dashboard', 'desktop'):
            return HTMLResponse('Not found', status_code=404)
        return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Saved — fictional QA</title><style>body{margin:0;--ui-bg-editor:#edf2f7;--ui-text-primary:#23384c;--ui-stroke-secondary:#b7c7d3;background:var(--ui-bg-editor)}nav{display:flex}</style><div id="root"></div><script type="module" src="/qa-assets/'+adapter+'.js"></script></html>')

    @ws.app.get('/delivery-shelf')
    @ws.app.get('/conversation-bookmarks')
    def saved_page():
        return page('dashboard')

    @ws.app.get('/qa-assets/{name}')
    def asset(name: str):
        if name not in ('dashboard.js', 'desktop.js'):
            return HTMLResponse('Not found', status_code=404)
        return FileResponse(qa / name)

    @ws.app.get('/api/qa/fixture')
    def fixture():
        return {'installed': installed, 'enabled': enabled, 'disabled': disabled, 'frontend': frontend}

    @ws.app.post('/api/qa/backend/{name}/{active}')
    def backend(name: str, active: bool):
        # Test-only policy control confined to this runner-owned fictional home.
        from fastapi import HTTPException
        if name not in installed:
            raise HTTPException(404)
        if active:
            if name not in enabled:
                enabled.append(name)
            if name in disabled:
                disabled.remove(name)
        else:
            if name in enabled:
                enabled.remove(name)
            if name not in disabled:
                disabled.append(name)
        (home / 'config.yaml').write_text('plugins:\n  isolation: in_process\n  enabled: '+json.dumps(enabled)+'\n  disabled: '+json.dumps(disabled)+'\n')
        return fixture()

    @ws.app.get('/api/qa/desktop/{name}')
    def desktop_asset(name: str):
        if name not in installed:
            return HTMLResponse('Not found', status_code=404)
        return FileResponse(home / 'plugins' / name / 'desktop' / 'plugin.js')

    routes = [r for r in ws.app.router.routes if getattr(r, 'path', '').startswith(('/qa/', '/qa-assets/', '/api/qa/', '/delivery-shelf', '/conversation-bookmarks'))]
    ws.app.router.routes[:] = routes + [r for r in ws.app.router.routes if r not in routes]
    uvicorn.run(ws.app, host='127.0.0.1', port=int(sys.argv[1]), log_level='warning', lifespan='off')
