"""Test-only native HTTP fixture. No schedulers or production installs."""
import os
from pathlib import Path
import sys
import tempfile
from native_probe import prepare, host, ROOT

with tempfile.TemporaryDirectory(prefix='dsb-', dir=os.environ.get('TMPDIR')) as directory:
    home=Path(directory)/'home'
    prepare(home)
    ws=host(home)
    from fastapi.responses import FileResponse, HTMLResponse
    from hermes_cli.web_server_dashboard import mount_spa
    import uvicorn
    qa=Path(sys.argv[2])

    @ws.app.get('/qa/{adapter}')
    def page(adapter:str):
        if adapter not in ('dashboard','desktop'):
            return HTMLResponse('Not found',status_code=404)
        return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Delivery Shelf — fictional QA</title><style>body{margin:0;--ui-bg-editor:#edf2f7;--ui-text-primary:#23384c;--ui-stroke-secondary:#b7c7d3;background:var(--ui-bg-editor)}</style><div id="root"></div><script type="module" src="/qa-assets/'+adapter+'.js"></script></html>')

    @ws.app.get('/qa-assets/{name}')
    def asset(name:str):
        if name not in ('dashboard.js','desktop.js','plugin.js'):
            return HTMLResponse('Not found',status_code=404)
        return FileResponse(qa/name)

    # web_server imports a pre-mounted SPA in this installed host. Keep fixture
    # pages ahead of its catch-all, just as native plugin hot-mounting does.
    qa_routes=[r for r in ws.app.router.routes if getattr(r,'path','').startswith(('/qa/','/qa-assets/'))]
    ws.app.router.routes[:]=qa_routes+[r for r in ws.app.router.routes if r not in qa_routes]
    mount_spa(ws.app)
    # This tests the native router and auth, not host startup/worker scheduling.
    uvicorn.run(ws.app,host='127.0.0.1',port=int(sys.argv[1]),log_level='warning',lifespan='off')
