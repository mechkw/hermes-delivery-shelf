"""Concrete per-entry version offers and scoped conversational approval."""
from contextlib import contextmanager
import json
import hashlib
import secrets
import time

from .recent_artifacts import recent, candidates, generation_request
from .telegram_shelf import session_identity


class Versions:
    def __init__(self, controller):
        self.controller, self.awareness = controller, controller.awareness
        self.api, self.home = controller.api, controller.home
        self.lease = secrets.token_hex(16)

    @contextmanager
    def connect(self):
        with self.awareness.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS version_offers(token TEXT PRIMARY KEY, '
                'entry_id TEXT NOT NULL, payload TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0)')
            conn.execute('CREATE TABLE IF NOT EXISTS version_permissions(entry_id TEXT NOT NULL, owner TEXT NOT NULL, '
                'PRIMARY KEY(entry_id,owner))')
            yield conn

    def identity(self, session_id):
        identity = session_identity()
        if identity['session_id']:
            if session_id and session_id != identity['session_id']:
                raise ValueError('Shelf session mismatch')
        else:
            identity = self.controller.identity(None, session_id, '', 'cli')
        self.authorize(identity)
        return identity

    def authorize(self, identity):
        self.awareness.authorize(identity['session_id'])
        if identity['profile'] != self.controller.profile:
            raise ValueError('Shelf profile changed')
        if identity['platform'] == 'telegram' and not self.controller.permitted(identity):
            raise ValueError('Shelf Telegram owner or session changed')

    @staticmethod
    def owner(identity):
        return json.dumps([identity['platform'], identity['user']], separators=(',', ':'))

    def offer(self, args, session_id=None):
        if not {'id','file'} <= set(args) or set(args) - {'id','file','replaces'}:
            raise ValueError('Use an exact saved ID and new file reference')
        identity = self.identity(session_id)
        store = self.api.Store(self.home)
        entry = store.get(args['id'])
        ref = self.api.FileRef.model_validate(args['file'])
        if entry.get('state', 'active') != 'active':
            return {'ok':True, 'status':'paused', 'saved':False, 'notify_user':False}
        delivery = recent(self.home, self.controller.profile, identity['session_id'])
        if delivery is None or ref.model_dump() not in candidates(self.api, self.home, delivery):
            raise ValueError('Offer only a concrete newly delivered file in this conversation')
        with self.api.open_file(self.home, ref) as stream:
            digest = hashlib.sha256(stream.read(self.api.MAX_FILE + 1)).hexdigest()
        current = entry['versions'][-1]['files'] if entry['versions'] else []
        replacement = self.api.FileRef.model_validate(args['replaces']).model_dump() if 'replaces' in args else ref.model_dump()
        if replacement not in entry['files']:
            if 'replaces' in args or len(entry['files']) != 1:
                raise ValueError('Specify replaces: the exact saved member this new file replaces; companions remain saved')
            replacement = entry['files'][0]
        index = entry['files'].index(replacement)
        if index < len(current) and digest == current[index]['sha256']:
            return {'ok':True, 'status':'unchanged', 'notify_user':False, 'saved':False}

        source = generation_request(self.api, delivery, ref.model_dump(), identity['session_id']).source.model_dump()
        payload = {'identity':identity, 'revision':entry['revision'], 'file':ref.model_dump(),
            'stamp':self.api.file_stamp(self.home, ref), 'source':source, 'replace_file':replacement,
            'sha256':digest, 'index':index,
            'lease':self.lease, 'epoch':self.controller.epoch}
        self.authorize(identity)
        token = secrets.token_hex(16)
        with self.connect() as conn:
            conn.execute('DELETE FROM version_offers WHERE expires<? OR used=1', (time.time(),))
            conn.execute('INSERT INTO version_offers(token,entry_id,payload,expires) VALUES(?,?,?,?)',
                (token,entry['id'],json.dumps(payload),time.time()+600))
            standing = conn.execute('SELECT 1 FROM version_permissions WHERE entry_id=? AND owner=?',
                (entry['id'],self.owner(identity))).fetchone() is not None
        if standing:
            return self.respond({'offer_id':token, 'decision':'yes'}, session_id=session_id)
        return {'ok':True, 'status':'offered', 'saved':False, 'offer_id':token, 'id':entry['id'],
            'title':entry['title'], 'file':ref.model_dump(), 'replaces':replacement,
            'message':f"Save {ref.path} as a new version of {entry['title']} in Delivery Shelf? "
                'Yes / Always for this delivery / Keep current.'}

    def respond(self, args, session_id=None):
        if set(args) != {'offer_id','decision'} or args['decision'] not in ('yes','always','keep'):
            raise ValueError('Use the exact offer and the user’s yes, always, or keep decision')
        identity = self.identity(session_id)
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM version_offers WHERE token=?', (args['offer_id'],)).fetchone()
        if row is None or row['used'] or row['expires'] <= time.time():
            raise ValueError('Shelf offer expired or already handled; offer again')
        offer = json.loads(row['payload'])
        if (offer['identity'] != identity or offer['lease'] != self.lease or
                offer['epoch'] != self.controller.epoch):
            raise ValueError('Shelf offer belongs to another session or lifecycle')
        def claim():
            self.authorize(identity)
            if offer['epoch'] != self.controller.epoch:
                raise ValueError('Shelf session changed')
            with self.connect() as conn:
                if conn.execute('UPDATE version_offers SET used=1 WHERE token=? AND used=0 AND expires>?',
                        (args['offer_id'],time.time())).rowcount != 1:
                    raise ValueError('Shelf offer expired or already handled')
        if args['decision'] == 'keep':
            claim()
            return {'ok':True, 'status':'kept', 'saved':False}
        store = self.api.Store(self.home)
        old = store.get(row['entry_id'])
        if old['revision'] != offer['revision'] or old.get('state','active') != 'active':
            raise ValueError('Saved delivery changed or is not active; nothing updated')
        ref = self.api.FileRef.model_validate(offer['file'])
        request = self.api.VersionInput.model_validate({'revision':offer['revision'], 'files':[offer['file']],
            'replace_file':offer['replace_file'],
            'session_id':identity['session_id'], 'sources':[{'file':offer['file'], 'source':offer['source'],
                'session_id':identity['session_id']}]})
        def authorize_commit():
            self.authorize(identity)
            current = store.get(old['id'])
            if current['revision'] != offer['revision'] or current.get('state','active') != 'active':
                raise ValueError('Saved delivery changed or is not active')
            self.api.source_module('artifact_source').resolve(self.api.source_api(),
                self.api.source_module('native_history'), self.home, identity['session_id'],
                self.api.ArtifactOrigin.model_validate(offer['source']), ref)
            if list(self.api.file_stamp(self.home, ref)) != offer['stamp']:
                raise ValueError('Offered file changed; nothing updated')
            with self.api.open_file(self.home, ref) as stream:
                if hashlib.sha256(stream.read(self.api.MAX_FILE + 1)).hexdigest() != offer['sha256']:
                    raise ValueError('Offered file changed; nothing updated')
            claim()
        updated = store.add_version(old['id'], request, authorize_commit=authorize_commit)
        self.authorize(identity)
        if store.get(old['id']) != updated or updated['revision'] != old['revision']+1:
            raise ValueError('Save outcome uncertain; inspect this exact delivery before retrying')
        if args['decision'] == 'always':
            with self.connect() as conn:
                conn.execute('INSERT OR IGNORE INTO version_permissions VALUES(?,?)',
                    (old['id'],self.owner(identity)))
        self.awareness.remember(updated, identity['session_id'])
        return {'ok':True, 'status':'saved', 'saved':True, 'data':updated,
            'standing_permission':args['decision']=='always'}

    def run(self, operation, args, session_id=None):
        try:
            return json.dumps(getattr(self,operation)(args,session_id=session_id))
        except Exception as exc:
            from fastapi import HTTPException
            message = exc.detail if isinstance(exc, HTTPException) else str(exc)
            return json.dumps({'ok':False, 'error':message})
