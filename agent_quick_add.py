"""Explicit quick capture shared by native commands; no artifact/catalog discovery."""
import asyncio
import json
from pathlib import Path
import re

from .recent_artifacts import recent, candidates, metadata, supplied_metadata, generation_request, MISSING


def parse_add(raw):
    count = None
    selector = re.match(r'^r([0-9]+)(?:\s|$)', raw)
    if selector:
        if not re.fullmatch(r'[1-8]', selector[1]):
            raise ValueError('Use /shelf add r1 through r8. Nothing saved.')
        count, raw = int(selector[1]), raw[selector.end():].strip()
    return count, supplied_metadata(raw)


def exact_entry(store, ref):
    """Lookup one literal primary reference, never enumerate the catalog."""
    with store.connect() as conn:
        row = conn.execute("SELECT id FROM entries WHERE json_extract(payload,'$.file.root')=? "
            "AND json_extract(payload,'$.file.path')=? ORDER BY created,id LIMIT 1",
            (ref['root'], ref['path'])).fetchone()
    return store.get(row['id']) if row else None


def save(controller, identity, raw, authorize, loop, *, on_commit_authorized):
    api, home = controller.api, controller.home
    count, supplied = parse_add(raw)
    authorize()
    delivery = recent(home, controller.profile, identity['session_id'], count=count)
    if delivery is None:
        raise ValueError(MISSING)
    authorize()
    refs = candidates(api, home, delivery)
    store = api.Store(home)
    known = exact_entry(store, refs[0])
    authorize()
    settings = store.settings() if callable(getattr(store, 'settings', None)) else {}
    generate = settings.get('generate_metadata', True)
    drafts, stamps, sources = [], [], []
    for ref in refs:
        authorize()
        entry = metadata(api, ref, identity['session_id'], supplied)
        stamp = api.file_stamp(home, api.FileRef.model_validate(ref))
        request = generation_request(api, delivery, ref, identity['session_id'])
        sources.append({'file': ref, 'source': request.source.model_dump()})
        missing = [key for key in ('title', 'description', 'tags') if key not in supplied]
        if missing and generate and known is None:
            request = api.GenerationRequest.model_validate(request.model_dump() | {
                'requested_fields': missing, 'supplied_metadata': supplied,
                'previous_exchanges': settings.get('context_messages', 10)})
            async def generate_one(request=request):
                authorize()
                result = await api.generate_draft(request, store)
                authorize()
                return result
            future = asyncio.run_coroutine_threadsafe(generate_one(), loop)
            try:
                result = future.result(timeout=api.GENERATION_TIMEOUT + 5)
            except BaseException:
                future.cancel()
                raise
            entry = api.EntryInput.model_validate(entry.model_dump() | {
                key: result['draft'][key] for key in missing})
        authorize()
        if stamp != api.file_stamp(home, api.FileRef.model_validate(ref)):
            raise ValueError('File changed during metadata generation. Nothing saved.')
        drafts.append(entry)
        stamps.append(stamp)
    payload = drafts[0].model_dump() | {'file':refs[0], 'files':refs, 'sources':sources}
    if len(refs) > 1:
        if 'title' not in supplied:
            suffix = f' (+{len(refs)-1} files)'
            payload['title'] = drafts[0].title[:160-len(suffix)] + suffix
        if 'description' not in supplied:
            payload['description'] = '\n'.join(Path(ref['path']).name+': '+draft.description
                for ref, draft in zip(refs, drafts))[:4000]
        if 'tags' not in supplied:
            payload['tags'] = list(dict.fromkeys(tag for draft in drafts for tag in draft.tags))[:20]
    entry = api.SourceCollection.model_validate(payload)
    def commit():
        authorize()
        current = recent(home, controller.profile, identity['session_id'], cutoff=delivery.cutoff, count=count)
        if current != delivery or candidates(api, home, current) != refs:
            raise ValueError('Recent delivery changed. Use /shelf add again.')
        if known is not None:
            # Generation was skipped only because this exact registration existed.
            # Concurrent deletion/retargeting must never create a placeholder.
            still = store.get(known['id'])
            if still['file'] != refs[0]:
                raise ValueError('Saved delivery changed. Use /shelf add again.')
        for ref, stamp in zip(refs, stamps):
            if api.file_stamp(home, api.FileRef.model_validate(ref)) != stamp:
                raise ValueError('File changed before save. Nothing saved.')
        authorize()
        on_commit_authorized()
    item, existing = store.register_file_once(entry, authorize_commit=commit)
    authorize()
    if store.get(item['id']) != item:
        raise ValueError('Readback changed; inspect saved deliveries before retrying.')
    if hasattr(controller, 'awareness'):
        controller.awareness.remember(item, identity['session_id'])
    if existing and item['files'] != refs:
        return 'Primary file already saved with a different set; nothing overwritten. Use Add version to approve a new version.'
    return ('Already saved to Delivery Shelf: ' if existing else 'Saved to Delivery Shelf: ') + item['title']
