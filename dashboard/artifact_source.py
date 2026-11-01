"""Explicit Desktop file candidates and bounded content, independent of Telegram."""
import codecs
import hashlib
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from fastapi import HTTPException

WINDOW = 500
MESSAGE_BYTES = 65536
IMAGE_BYTES = 4 * 1024 * 1024
TEXT_BYTES = 65536
IMAGE_TYPES = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.gif':'image/gif', '.webp':'image/webp'}


def paths(history, content):
    # Project known visible rich blocks and scrub private carriers BEFORE looking
    # for explicit delivery syntax. Ordinary filesystem prose is never a source.
    text = history.source_preview(content, limit=None, keep_lines=True)
    result, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(('```','~~~')):
            fence = not fence
            continue
        if fence:
            continue
        match = re.fullmatch(r'MEDIA:\s*(/[^\r\n]+)', line.strip())
        refs = [match[1]] if match else []
        refs += [m[1] for m in re.finditer(r'\[[^\]\n]{1,200}\]\((?:sandbox:)?(/[^\s)]+)\)', line)]
        for value in refs:
            if value not in result:
                result.append(value)
        if len(result) > 8:
            raise HTTPException(422, 'Too many file references in one delivery')
    return result


def reference(api, home, raw):
    path = Path(raw)
    if not path.is_absolute() or any(p in ('', '.', '..') for p in raw.split('/')[1:]):
        raise HTTPException(403, 'File reference is unsafe')
    roots = api.allowed_roots(home)
    matches = sorted(((alias, root) for alias, root in roots.items() if path.is_relative_to(root)),
                     key=lambda pair: (-len(pair[1].parts), pair[0]))
    if not matches:
        raise HTTPException(403, 'File is outside approved Shelf locations')
    alias, root = matches[0]
    ref = api.FileRef(root=alias, path=path.relative_to(root).as_posix())
    with api.open_file(home, ref):
        pass
    return ref


def candidates(api, history, home, session_id, q='', limit=30, offset=0):
    source = history.SourceAdapter(home)
    with source.chooser_connection() as conn:
        source.chooser_schema(conn, {'sessions':('id','profile_name','hidden','source','model_config','parent_session_id','end_reason'),
            'messages':('id','session_id','content','role','active','compacted','display_kind','observed','_compressed_summary','tool_calls','display_metadata')})
        history.conversation_lineage(conn, home, session_id)
        rows=conn.execute('''SELECT id, CASE WHEN typeof(content)='text' AND length(CAST(content AS BLOB))<=?
            THEN content END AS content FROM messages WHERE session_id=? AND role='assistant'
            AND history_row_eligible(role,active,compacted,display_kind,observed,_compressed_summary,
                substr(display_metadata,1,4097),substr(tool_calls,1,64))=1
            ORDER BY id DESC LIMIT ?''',(MESSAGE_BYTES,session_id,WINDOW+1)).fetchall()
    items, skipped = [], 0
    for row in rows[:WINDOW]:
        if row['content'] is None:
            skipped += 1
            continue
        digest=hashlib.sha256(row['content'].encode()).hexdigest()
        for raw in paths(history,row['content']):
            try:
                ref=reference(api,home,raw)
            except (HTTPException, ValueError):
                skipped += 1
                continue
            identity=hashlib.sha256(json.dumps([session_id,row['id'],digest,ref.model_dump()],sort_keys=True).encode()).hexdigest()
            name=Path(ref.path).name
            items.append({'id':identity,'name':name,'type':Path(name).suffix[1:].upper(),
                'file':ref.model_dump(),'source':{'message_id':row['id'],'digest':digest,'artifact_id':identity},
                'content_mode':'text' if Path(name).suffix.lower() in api.TEXT_TYPES else 'image' if Path(name).suffix.lower() in IMAGE_TYPES else 'history-only'})
    result=history.source_page(items,q,limit,offset,WINDOW,len(rows)>WINDOW,('name','type'))
    result['unavailable']=skipped
    return result


def resolve(api, history, home, session_id, selected, ref=None):
    # Exact origin revalidation, independent of current result-page ordering.
    source=history.SourceAdapter(home)
    with source.chooser_connection() as conn:
        history.conversation_lineage(conn, home, session_id)
        row=conn.execute('''SELECT CASE WHEN typeof(content)='text' AND length(CAST(content AS BLOB))<=?
            THEN content END AS content FROM messages WHERE session_id=? AND id=? AND role='assistant'
            AND history_row_eligible(role,active,compacted,display_kind,observed,_compressed_summary,
                substr(display_metadata,1,4097),substr(tool_calls,1,64))=1''',
            (MESSAGE_BYTES,session_id,selected.message_id)).fetchone()
    if row is None or row['content'] is None or hashlib.sha256(row['content'].encode()).hexdigest()!=selected.digest:
        raise HTTPException(409,'Delivery source changed or was removed. Choose the file again.')
    for raw in paths(history,row['content']):
        try:
            found=reference(api,home,raw)
        except (HTTPException,ValueError):
            continue
        identity=hashlib.sha256(json.dumps([session_id,selected.message_id,selected.digest,found.model_dump()],sort_keys=True).encode()).hexdigest()
        if identity==selected.artifact_id and (ref is None or found==ref):
            return found
    raise HTTPException(409,'Selected file is no longer available under the current policy')


def file_input(api, home, ref):
    suffix=Path(ref.path).suffix.lower()
    if suffix not in api.TEXT_TYPES and suffix not in IMAGE_TYPES:
        return [], 'history-only', False
    cap=TEXT_BYTES if suffix in api.TEXT_TYPES else IMAGE_BYTES
    with api.open_file(home,ref) as stream:
        before=os.fstat(stream.fileno())
        content=stream.read(cap+1)
        after=os.fstat(stream.fileno())
    if (before.st_mtime_ns,before.st_ctime_ns,before.st_size)!=(after.st_mtime_ns,after.st_ctime_ns,after.st_size):
        raise HTTPException(409, 'File changed while reading. Generate again.')
    if suffix in api.TEXT_TYPES:
        try:
            text=codecs.getincrementaldecoder('utf-8')('strict').decode(content[:cap], final=len(content)<=cap)
        except UnicodeDecodeError:
            return [], 'history-only (not UTF-8)', False
        return [{'type':'text','text':json.dumps({'file_name':Path(ref.path).name,'file_text':text})}], 'text', len(content)>cap
    if len(content)>cap:
        return [], 'history-only (image exceeds 4 MiB)', False
    # Header validation before asking the native provider to decode any bytes.
    mime=image_mime(content)
    if mime != IMAGE_TYPES[suffix]:
        return [], 'history-only (unsupported image content)', False
    return [{'type':'image','data':content,'mime_type':mime,'file_name':Path(ref.path).name}], 'image', False


def image_mime(content):
    if content.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if content.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if content.startswith((b'GIF87a',b'GIF89a')): return 'image/gif'
    if content[:4]==b'RIFF' and content[8:12]==b'WEBP': return 'image/webp'
    return None
