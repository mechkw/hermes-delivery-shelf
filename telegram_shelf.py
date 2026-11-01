"""Profile-owned PTB panels. No bot credentials, adapter internals or file watchers."""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import stat
import threading
import time
from dataclasses import dataclass, field

TTL = 600
CAPACITY = 128
PAGE = 5
GUIDANCE = (
    "Delivery Shelf: after producing a concrete NEW derivative of an already registered file, "
    "call delivery_shelf_offer_update with that known entry ID and the explicit new root/path. "
    "Never scan for candidates. Same-path edits are silent: do not notify or offer. "
    "An offer is NOT a save; only the user's Update registration button authorizes retargeting. "
    "Keep current leaves the registration unchanged. Never use delivery_shelf_update to bypass "
    "this consent. For a Shelf Add request, copy its request_id into every delivery_shelf_register "
    "call and use its exact session_id; then search/read back each saved ID before reporting success. "
    "If no recent artifact is identifiable from current conversation context, ask rather than guess."
)


def session_identity():
    from gateway.session_context import get_session_env, bound_session_key
    # The accessor's legacy CLI fallback reads process environment. Native flows
    # require a task-bound route, never that ambient fallback.
    if not bound_session_key():
        return {key: '' for key in ('platform', 'session_id', 'session_key', 'profile', 'user', 'chat', 'thread', 'anchor')}
    return {key: str(get_session_env('HERMES_SESSION_' + name) or '') for key, name in (
        ('platform', 'PLATFORM'), ('session_id', 'ID'), ('session_key', 'KEY'),
        ('profile', 'PROFILE'), ('user', 'USER_ID'), ('chat', 'CHAT_ID'),
        ('thread', 'THREAD_ID'), ('anchor', 'MESSAGE_ID'))}


@dataclass
class Panel:
    identity: dict
    generation: int
    expires: float
    message: str = ''
    actions: dict = field(default_factory=dict)
    offer: dict | None = None
    busy: bool = False
    consumed: bool = False


class Controller:
    def __init__(self, ctx, api):
        self.ctx, self.api = ctx, api
        self.home = api.bound_home()
        self.profile = getattr(ctx, 'profile_name', api.profile_name(self.home))
        self.lock = threading.RLock()
        self.application = self.loop = None
        self.generation = 0
        self.alive = True
        self.panels, self.requests, self.seen = {}, {}, {}
        self.epoch = 0
        self.retired_sessions = set()
        self.session_fenced = False

    def owners(self):
        """Separate operator policy, re-read on EVERY interaction, fail closed."""
        path = self.home / 'plugin-data' / 'delivery-shelf' / 'telegram-owners.json'
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                meta = os.fstat(stream.fileno())
                if not stat.S_ISREG(meta.st_mode) or meta.st_size > 4096:
                    return set()
                value = json.loads(stream.read(4097))
            if not isinstance(value, list) or len(value) > 50 or any(
                not isinstance(v, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', v) for v in value
            ):
                return set()
            return set(value)
        except (OSError, ValueError, AttributeError):
            return set()

    def prune(self):
        now = time.monotonic()
        for collection in (self.panels, self.requests, self.seen):
            for key, value in list(collection.items()):
                expires = value.expires if isinstance(value, Panel) else value['expires']
                if expires <= now:
                    del collection[key]
            while len(collection) >= CAPACITY:
                del collection[next(iter(collection))]

    def close(self):
        with self.lock:
            self.alive = False
            self.panels.clear()
            self.requests.clear()
            self.seen.clear()

    def boundary(self, session_id=None, old_session_id=None, deleted_ids=None, reset=False, **kwargs):
        with self.lock:
            self.epoch += 1
            ids = {v for v in (session_id, old_session_id, *(deleted_ids or [])) if v}
            retired = {old_session_id} if reset and old_session_id else (ids if not reset else set())
            if len(self.retired_sessions | retired) > CAPACITY:
                # Never evict an invalid generation and accidentally admit its pinned old turn.
                self.session_fenced = True
            else:
                self.retired_sessions.update(retired)
            if reset and not old_session_id:
                self.session_fenced = True  # Cannot prove which prior generation was retired.
                ids = set()
            for collection in (self.panels, self.requests):
                for key, value in list(collection.items()):
                    identity = value.identity if isinstance(value, Panel) else value['identity']
                    if not ids or identity['session_id'] in ids:
                        del collection[key]

    def factory(self, application, adapter):
        from telegram.ext import CallbackQueryHandler
        with self.lock:
            if not self.alive:
                return
            self.generation += 1
            self.epoch += 1
            self.panels.clear()
            self.requests.clear()
            self.seen.clear()
            self.application = application
            self.loop = asyncio.get_running_loop()
            generation = self.generation
        async def callback(update, context):
            await self.callback(update, context, generation)
        application.add_handler(CallbackQueryHandler(callback, pattern=r'^shelf:'))

    def identity(self, source, session_id, session_key, platform):
        return dict(platform=platform or '', session_id=session_id or '', session_key=session_key or '',
                    profile=self.profile if self.api.bound_home() == self.home else '', user=str(getattr(source, 'user_id', '') or ''),
                    chat=str(getattr(source, 'chat_id', '') or ''),
                    thread=str(getattr(source, 'thread_id', '') or ''),
                    anchor=str(getattr(source, 'message_id', '') or ''))

    def _permitted(self, identity, owners):
        """Memory-only check. Never hold the state lock across disk/host calls."""
        return (self.alive and not self.session_fenced and identity['session_id'] not in self.retired_sessions and
                identity['profile'] == self.profile and
                identity['platform'] == 'telegram' and identity['user'] in owners and
                re.fullmatch(r'-?[1-9][0-9]*', identity['chat']) and
                (not identity['thread'] or re.fullmatch(r'[1-9][0-9]*', identity['thread'])) and
                bool(identity['session_id'] and identity['session_key']))

    def permitted(self, identity):
        owners = self.owners()
        with self.lock:
            return self._permitted(identity, owners)

    def handoff_error(self, identity):
        if not self.permitted(identity):
            return 'Delivery Shelf not saved: authorized current session and Telegram owner policy required.'
        # v0.22.5 keyed injection restores the first participant; origin injection
        # can later fail the authority's exact committed-source check. No public
        # prequeue API pins both the current generation and initiating participant.
        if identity['chat'].startswith('-'):
            return ('Delivery Shelf not saved: shared-group agent handoff cannot safely bind the clicking owner '
                    'on this host. Nothing queued. Supply title, #tags and --description with --file, '
                    'or request Add in a private chat. Existing update/keep panels still work.')
        return None

    def new_request(self, identity, supplied=None):
        with self.lock:
            self.prune()
            token = secrets.token_hex(16)
            self.requests[token] = dict(identity=identity.copy(), expires=time.monotonic() + TTL,
                                        files=set(), generation=self.generation,
                                        supplied=json.loads(json.dumps(supplied or {})))
            return token

    def register_guarded(self, args, run):
        args = dict(args)
        token = args.pop('request_id', None)
        current = session_identity()

        def authorize_commit():
            # Store calls again AFTER SQLite's write wait and file-policy validation.
            owners, home = self.owners(), self.api.bound_home()
            with self.lock:
                self.prune()
                if not self.alive:
                    raise ValueError('Shelf controller unloaded')
                if current['platform'] == 'telegram' and (self.session_fenced or current['session_id'] in self.retired_sessions):
                    raise ValueError('Retired or unverified session generation; request from a fresh active session')
                if token is not None:
                    request = self.requests.get(token) if isinstance(token, str) else None
                    if (not request or request['generation'] != self.generation or home != self.home or any(
                            request['identity'][key] != current[key] for key in
                            ('session_id', 'session_key', 'profile', 'platform', 'user', 'chat', 'thread')) or
                            not self._permitted(current, owners) or args.get('session_id') != current['session_id']):
                        raise ValueError('Shelf request expired or session changed; request Add again')
                    if any(args.get(k) != v for k, v in request['supplied'].items()):
                        raise ValueError('Preserve the explicit request file and supplied metadata')
                    ref = args.get('file')
                    if not isinstance(ref, dict):
                        raise ValueError('A concrete file is required for Add')
                    key = json.dumps(ref, sort_keys=True)
                    if key in request['files'] or len(request['files']) >= 32:
                        raise ValueError('Request already registered this file or reached its 32-file limit; search for readback')
                    # This is the commit-authorization point, not a success claim.
                    # Retain the one-shot claim even if subsequent commit/readback fails.
                    request['files'].add(key)
                else:
                    if current['session_id'] and args.get('session_id') not in (None, '', current['session_id']):
                        raise ValueError('Session generation mismatch')
                    if any(r['identity']['session_key'] == current['session_key'] and current['session_key']
                           for r in self.requests.values()):
                        raise ValueError('Use the current Shelf request_id')
        return run('register', args, authorize_commit=authorize_commit)

    def keyboard(self, token, panel, offset=0, detail=None):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        actions, rows = {}, []
        def row(label, action):
            key = str(len(actions))
            actions[key] = action
            rows.append([InlineKeyboardButton(label, callback_data=f'shelf:{token}:{key}')])
        # This host cannot safely admit assisted Add from a shared group.
        # Keep the text command's refusal, but do not offer a dead-end button.
        if not panel.identity['chat'].startswith('-'):
            row('Add', ('add', None))
        if detail:
            entry = self.api.Store(self.home).get(detail)
            text = ('Shelf · Details\n' + entry['title'] + '\n' + entry['description'][:1800] +
                    '\nTags: ' + ', '.join(entry['tags']) + '\nID: ' + entry['id'])
            if entry['file']:
                text += '\nFile: ' + entry['file']['root'] + ':' + entry['file']['path']
            row('Back to recent', ('page', 0))
        else:
            data = self.api.Store(self.home).search(limit=PAGE, offset=offset)
            text = f"Shelf · {data['total']} saved"
            for entry in data['items']:
                row(entry['title'][:60], ('detail', entry['id']))
            if offset:
                row('Previous', ('page', max(0, offset - PAGE)))
            row('Browse more', ('page', offset + PAGE if offset + PAGE < data['total'] else 0))
        panel.actions = actions
        return text, InlineKeyboardMarkup(rows)

    def _prepare_send(self, identity, offer, epoch):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        owners = self.owners()
        with self.lock:
            self.prune()
            if self.session_fenced:
                return 'Shelf inline panels unavailable: session-generation guard exhausted or incomplete; restart the owning gateway before using panels.'
            if epoch is not None and epoch != self.epoch:
                return 'Shelf session changed before delivery; request again.'
            if not self._permitted(identity, owners) or self.application is None:
                return 'Shelf inline panels unavailable: configure the Telegram owner policy and use an active session, or use explicit /shelf commands.'
            token = secrets.token_hex(12)
            panel = Panel(identity.copy(), self.generation, time.monotonic() + TTL, offer=offer)
            self.panels[token] = panel
            application = self.application
        if offer:
            panel.actions = {'0': ('update', None), '1': ('keep', None)}
            text = 'Shelf · Update available\n' + offer['entry']['title'] + '\n' + offer['file']['path']
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton('Update registration', callback_data=f'shelf:{token}:0')],
                [InlineKeyboardButton('Keep current', callback_data=f'shelf:{token}:1')]])
        else:
            text, markup = self.keyboard(token, panel)
        # Catalog/policy reads may have waited; do not revive a retired panel.
        if not self._panel_current(token, panel, epoch):
            return 'Shelf session changed before delivery; request again.'
        return token, panel, application, text, markup

    def _panel_current(self, token, panel, epoch=None):
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            return (self.panels.get(token) is panel and panel.expires > time.monotonic() and
                    (epoch is None or epoch == self.epoch) and
                    panel.generation == self.generation and home == self.home and
                    self._permitted(panel.identity, owners))

    def _finish_send(self, token, panel, message, epoch):
        current = self._panel_current(token, panel, epoch)
        with self.lock:
            if not current or self.panels.get(token) is not panel:
                self.panels.pop(token, None)
                return 'Shelf panel expired during delivery; request again.'
            if str(message.chat.id) != panel.identity['chat'] or str(message.message_thread_id or '') != panel.identity['thread']:
                self.panels.pop(token, None)
                return 'Shelf transport returned an unexpected route; panel disabled.'
            panel.message = str(message.message_id)

    def _drop_panel(self, token):
        with self.lock:
            self.panels.pop(token, None)

    async def send(self, identity, offer=None, epoch=None):
        from telegram import ReplyParameters
        prepared = await asyncio.to_thread(self._prepare_send, identity, offer, epoch)
        if isinstance(prepared, str):
            return prepared
        token, panel, application, text, markup = prepared
        kwargs = dict(chat_id=int(identity['chat']), text=text, reply_markup=markup, parse_mode=None)
        if identity['thread']:
            kwargs['message_thread_id'] = int(identity['thread'])
        if identity['anchor'] and identity['anchor'].isdigit():
            kwargs['reply_parameters'] = ReplyParameters(message_id=int(identity['anchor']), allow_sending_without_reply=False)
        try:
            message = await application.bot.send_message(**kwargs)
            return await asyncio.to_thread(self._finish_send, token, panel, message, epoch)
        except BaseException:
            await asyncio.to_thread(self._drop_panel, token)
            raise

    def _claim(self, query, application, generation):
        from telegram import Message
        match = re.fullmatch(r'shelf:([a-f0-9]{24}):([0-9]{1,2})', query.data if isinstance(query.data, str) else '')
        message, owners, home = query.message, self.owners(), self.api.bound_home()
        with self.lock:
            self.prune()
            panel = self.panels.get(match[1]) if match else None
            valid = (panel is not None and match is not None and self.alive and generation == self.generation == panel.generation and
                     application is self.application and home == self.home and isinstance(message, Message) and message.is_accessible and
                     str(query.from_user.id) == panel.identity['user'] and
                     str(message.chat.id) == panel.identity['chat'] and
                     str(getattr(message, 'message_thread_id', None) or '') == panel.identity['thread'] and
                     str(message.message_id) == panel.message and self._permitted(panel.identity, owners) and
                     not panel.busy and not panel.consumed and match[2] in panel.actions)
            if valid and panel is not None and match is not None:
                panel.busy = True
                return match[1], panel, panel.actions[match[2]]
        return None

    def _authorize_panel_commit(self, token, panel, *, request=False):
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            if (self.panels.get(token) is not panel or panel.expires <= time.monotonic() or
                    panel.generation != self.generation or home != self.home or
                    not self._permitted(panel.identity, owners) or not panel.busy or panel.consumed):
                raise ValueError('Shelf action expired or session changed')
            # Atomic lifecycle/one-shot claim, AFTER write-lock and policy waits.
            # Once authorized, a commit may finish after reset; never pretend rollback.
            panel.consumed = True
            if request:
                return self.new_request(panel.identity)

    def _perform(self, token, panel, action, value):
        if not self._panel_current(token, panel):
            return None
        if action == 'add':
            error = self.handoff_error(panel.identity)
            if error:
                return error, None
            request = self._authorize_panel_commit(token, panel, request=True)
            from . import _recent_add_command
            result = _recent_add_command(self.ctx, session_id=panel.identity['session_id'],
                                         session_key=panel.identity['session_key'], platform='telegram', request_id=request)
            if result is not None:
                with self.lock:
                    self.requests.pop(request, None)
                return result, None
            return 'Shelf · Requested\nQueued for the current conversation. Nothing saved yet.', None
        if action in ('page', 'detail'):
            result = self.keyboard(token, panel, **({'offset': value} if action == 'page' else {'detail': value}))
            return result if self._panel_current(token, panel) else None
        if action == 'keep':
            self._authorize_panel_commit(token, panel)
            return 'Shelf · Kept current\nRegistration unchanged.', None
        if action == 'update':
            offer = panel.offer
            assert offer is not None
            store = self.api.Store(self.home)
            old = offer['entry']
            payload = {k: old[k] for k in self.api.EntryInput.model_fields}
            payload.update(file=offer['file'], revision=old['revision'])
            updated = store.update(old['id'], self.api.EntryUpdate.model_validate(payload),
                                   authorize_commit=lambda: self._authorize_panel_commit(token, panel))
            verified = store.get(old['id'])
            if verified != updated or verified['revision'] != old['revision'] + 1 or verified['file'] != offer['file'] or any(
                    verified[k] != old[k] for k in self.api.EntryInput.model_fields if k != 'file'):
                raise ValueError('Readback changed; inspect the registration before retrying')
            return 'Shelf · Updated\n' + verified['title'] + '\nID: ' + verified['id'], None

    def _release(self, panel, terminal=False):
        with self.lock:
            panel.busy = False
            if terminal:
                panel.consumed = True

    async def callback(self, update, context, generation):
        query = update.callback_query
        if query is None:
            return
        claimed = await asyncio.to_thread(self._claim, query, context.application, generation)
        if claimed is None:
            await query.answer('Shelf panel expired or not authorized.', show_alert=True)
            return
        token, panel, (action, value) = claimed
        try:
            await query.answer()
            result = await asyncio.to_thread(self._perform, token, panel, action, value)
            if result is not None:
                text, markup = result
                await query.edit_message_text(text=text, reply_markup=markup, parse_mode=None)
        except asyncio.CancelledError:
            # Cancelling to_thread does not stop its worker. Fence it before
            # releasing busy so a waiting write cannot authorize after cancellation.
            await asyncio.to_thread(self._drop_panel, token)
            raise
        except Exception:
            # A commit may have succeeded before transport/readback failed; never claim rollback.
            try:
                await query.edit_message_text(text='Shelf · Could not complete confirmation\nRefresh and inspect the registration before retrying; it may have changed.', reply_markup=None, parse_mode=None)
            except Exception:
                pass
        finally:
            await asyncio.to_thread(self._release, panel, action == 'update')

    def offer(self, args):
        with self.lock:
            epoch = self.epoch
        try:
            if not isinstance(args, dict) or set(args) != {'id', 'file'} or not re.fullmatch(r'[a-f0-9]{32}', args['id']):
                raise ValueError('Supply a known entry ID and one concrete file')
            if self.api.bound_home() != self.home:
                raise ValueError('Profile mismatch')
            entry = self.api.Store(self.home).get(args['id'])
            ref = self.api.FileRef.model_validate(args['file'])
            if not entry['file']:
                raise ValueError('The parent must have a registered file')
            # Path identity, not hash/mtime: same registered path is always silent.
            old_ref = self.api.FileRef.model_validate(entry['file'])
            roots = self.api.allowed_roots(self.home)
            if ref.model_dump() == entry['file'] or (ref.root in roots and old_ref.root in roots and
                    roots[ref.root] / ref.path == roots[old_ref.root] / old_ref.path):
                return json.dumps({'ok': True, 'status': 'same_file_silent', 'notify_user': False})
            with self.api.open_file(self.home, ref):
                pass
            identity = session_identity()
            if not self.permitted(identity) or self.application is None or not self.loop or not self.loop.is_running():
                return json.dumps({'ok': False, 'status': 'unsupported', 'error': 'No authorized Telegram inline transport. No offer sent and nothing changed. Ask for explicit confirmation, then use delivery_shelf_update with the latest revision.'})
            try:
                if asyncio.get_running_loop() is self.loop:
                    raise ValueError('Offer must run in the host tool worker, not its transport loop')
            except RuntimeError:
                pass
            key = (identity['session_id'], identity['session_key'], args['id'], ref.root, ref.path)
            with self.lock:
                self.prune()
                if key in self.seen:
                    return json.dumps({'ok': True, 'status': 'already_offered', 'saved': False})
                self.seen[key] = {'expires': time.monotonic() + TTL}
            future = asyncio.run_coroutine_threadsafe(self.send(identity, {'entry': entry, 'file': ref.model_dump()}, epoch=epoch), self.loop)
            try:
                error = future.result(timeout=20)
            except BaseException:
                future.cancel()
                with self.lock:
                    self.seen.pop(key, None)
                raise
            if error:
                with self.lock:
                    self.seen.pop(key, None)
                raise ValueError(error)
            return json.dumps({'ok': True, 'status': 'offered', 'saved': False})
        except Exception as exc:
            from fastapi import HTTPException
            return json.dumps({'ok': False, 'error': str(exc.detail) if isinstance(exc, HTTPException) else 'Offer unavailable or invalid; no confirmed update'})
