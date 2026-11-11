"""Immutable provenance captured per saved version, never guessed from latest refs."""
import json
from fastapi import HTTPException


def unknown():
    return dict(profile=None, session_id=None, message_id=None, original_root=None,
                original_path=None, source=None, known=False)


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS version_provenance (version_id TEXT PRIMARY KEY REFERENCES entry_versions(id) ON DELETE CASCADE, payload TEXT NOT NULL)')


def capture(api, store, refs, request):
    selections = list(getattr(request, 'sources', []) or [])
    source = getattr(request, 'source', None)
    if source and not selections and refs:
        selections = [api.SourceSelection(file=refs[0], source=source)]
    ref_keys = {(ref.root, ref.path) for ref in refs}
    keys = [(s.file.root, s.file.path) for s in selections]
    if len(set(keys)) != len(keys) or any(key not in ref_keys for key in keys):
        raise HTTPException(422, 'Per-file sources must match this version exactly')
    session = getattr(request, 'session_id', '') or None
    if selections and not session and any(not s.session_id for s in selections):
        raise HTTPException(422, 'A conversation is required for message provenance')
    sources = dict(zip(keys, selections))
    roots = api.allowed_roots(store.home)
    files = []
    for ref in refs:
        selected = sources.get((ref.root, ref.path))
        origin = selected.source.model_dump() if selected else None
        files.append(dict(profile=api.profile_name(store.home), session_id=(selected.session_id or session) if selected else session,
                          message_id=origin['message_id'] if origin else None, original_root=ref.root,
                          original_path=str(roots[ref.root] / ref.path), source=origin, known=True))
    sessions = {f['session_id'] for f in files}
    messages = {f['message_id'] for f in files}
    summary = dict(profile=api.profile_name(store.home), session_id=next(iter(sessions)) if len(sessions)==1 else None,
                   message_id=next(iter(messages)) if len(messages)==1 else None, known=True)
    return files, summary


def decode(conn, versions):
    for version in versions:
        row = conn.execute('SELECT payload FROM version_provenance WHERE version_id=?', (version['id'],)).fetchone()
        version['provenance'] = json.loads(row[0]) if row else unknown()
        for item in version['files']:
            item.setdefault('provenance', unknown())
    return versions
