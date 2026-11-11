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
NATIVE_UNAVAILABLE = (
    'Delivery Shelf · native Telegram buttons and downloads are not bound on this gateway. '
    'Nothing saved or sent. After a plugin reload, the operator must rebuild/restart the owning '
    'gateway native client; repeated plugin reloads cannot repair this host lifecycle gap. '
    'If plugin isolation is enabled, native handlers are unsupported; keep isolation unchanged.'
)
GUIDANCE = (
    "Delivery Shelf: after producing a concrete NEW derivative of an already registered file, "
    "call delivery_shelf_offer_update with that known entry ID and the explicit new root/path. "
    "Never scan for candidates. Newly delivered changed bytes, even at the same path, may be offered; unchanged bytes stay silent. "
    "For a multi-file delivery and a new path, supply replaces with the exact known saved member; ask if unclear. "
    "First save is ALWAYS deliberate. Return the exact version-offer question; an offer is NOT a save. "
    "After the user's conversational yes, call delivery_shelf_respond_update with the exact offer_id and yes. "
    "Their always authorizes subsequent concrete versions of THIS already-saved delivery only; use decision always. "
    "Keep current changes nothing. Never infer lineage from filenames, scan the catalog, or create a global auto-save permission. "
    "Never use delivery_shelf_update to bypass version approval. For a Shelf Add request, copy its request_id into every delivery_shelf_register "
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
    pending_items: list | None = None
    pending_actions: dict = field(default_factory=dict)
    action_generation: int = 0
    delivery: object = None
    recent_count: int | None = None
    candidates: list = field(default_factory=list)
    supplied: dict = field(default_factory=dict)
    version_target: dict | None = None
    version_selection: list = field(default_factory=list)
    version_stamps: list = field(default_factory=list)
    cancelled: threading.Event = field(default_factory=threading.Event)


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
        self.download_busy = set()
        self.snapshots = {}
        # One list publication per result context. Never evict active leases:
        # cancellation of to_thread does not stop the worker using its lease.
        self.publications = {}
        self.uncertain_publications = set()
        self.publication_fenced = False
        self.epoch = 0
        self.retired_sessions = set()
        self.session_fenced = False

    def start_cleanup(self, interval=60):
        self.cleanup_stop = threading.Event()
        def work():
            while not self.cleanup_stop.wait(interval):
                with self.lock:
                    if not self.alive:
                        return
                try:
                    self.api.Store(self.home).cleanup_due()
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Delivery Shelf scheduled cleanup failed')
        self.cleanup_thread = threading.Thread(target=work, name='delivery-shelf-cleanup', daemon=True)
        self.cleanup_thread.start()

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
        for collection in (self.panels, self.requests, self.seen, self.snapshots):
            for key, value in list(collection.items()):
                expires = value.expires if isinstance(value, Panel) else value['expires']
                if expires <= now:
                    del collection[key]
            while len(collection) >= CAPACITY:
                del collection[next(iter(collection))]

    def close(self):
        if hasattr(self, 'cleanup_stop'):
            self.cleanup_stop.set()
            self.cleanup_thread.join(timeout=2)
        with self.lock:
            self.alive = False
            self.panels.clear()
            self.requests.clear()
            self.seen.clear()
            self.snapshots.clear()

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
                # Startup/resume can omit the old ID. The epoch and removal of
                # every outstanding capability fence old work; they must not
                # permanently reject a freshly dispatched, session-bound Add.
                ids = set()
            for collection in (self.panels, self.requests, self.snapshots):
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
            self.snapshots.clear()
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
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            return home == self.home and self._permitted(identity, owners)

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

    def _stage_keyboard(self, token, panel, text, buttons):
        """Never reuse an action key or arm an unpublished replacement keyboard."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        with self.lock:
            panel.action_generation += 1
            if panel.action_generation > 0xffffffffffffffff:
                raise ValueError('Shelf panel exhausted; refresh it')
            generation = panel.action_generation
            actions, rows = {}, []
            for index, (label, action) in enumerate(buttons):
                key = (secrets.token_hex(4) if action[0] == 'download' else
                       str(index) if generation == 1 else f'{generation:x}.{index:x}')
                actions[key] = action
                rows.append([InlineKeyboardButton(label, callback_data=f'shelf:{token}:{key}')])
            panel.actions = {}
            panel.pending_actions = actions
        return text, InlineKeyboardMarkup(rows)


    def keyboard(self, token, panel, offset=0, detail=None, query=None, numbered=True):
        buttons = []
        panel.pending_items = None
        def row(label, action):
            buttons.append((label, action))
        row('Add', ('add', None))
        if detail:
            entry = self.api.Store(self.home).get(detail)
            text = ('Shelf · Details\n' + entry['title'] + '\n' + entry['description'][:1800] +
                    '\nTags: ' + ', '.join(entry['tags']))
            versions = entry.get('versions') or []
            current = next((v for v in versions if v['id'] == entry.get('current_version')), None)
            if current:
                files = current['files']
                text += f"\nVersion {current['number']} · {len(files)} file(s)"
                for number, item in enumerate(files, 1):
                    label = 'Send file' if len(files) == 1 else f"Send {number} · {item['name'][:43]}"
                    row(label, ('download', (entry['id'], entry['revision'], current['id'], item['id'])))
                if 1 < len(files) <= 5:
                    row('Send all files', ('download_set', (entry['id'], entry['revision'], current['id'])))
                row('Versions', ('versions', (entry['id'], entry['revision'], 0)))
            elif entry.get('file'):
                # Legacy availability is checked only by read_entry_file at send time.
                row('Send file', ('download', (entry['id'], entry['revision'])))
            else:
                text += '\nNo file attached.'
            row('Add version', ('add_version', (entry['id'], entry['revision'])))
            row('Back to recent', ('page', 0))
        else:
            data = self.api.Store(self.home).search(q=query or '', limit=20 if query is not None else PAGE, offset=offset)
            if not self._panel_current(token, panel):
                raise ValueError('Shelf list no longer authorized')
            text = (f"Delivery Shelf — {data['total']} matching deliveries" if query is not None
                    else f"Shelf · {data['total']} saved")
            if numbered:
                panel.pending_items = [(e['id'], e['revision']) for e in data['items']]
            for number, entry in enumerate(data['items'], 1):
                text += ('\n' + (f'{number}. ' if numbered else '• ') + entry['title'][:100] +
                         ('' if entry['file'] else ' · no file attached'))
                row(entry['title'][:60], ('detail', entry['id']))
            text += ('\n/shelf dl <number> — send from this page (10 minutes)' if numbered else
                     '\nNumbered downloads disabled after unconfirmed delivery. Select an entry → Send file; or use Desktop/Dashboard.')
            if offset and query is None:
                row('Previous', ('page', max(0, offset - PAGE)))
            if query is None:
                row('Browse more', ('page', offset + PAGE if offset + PAGE < data['total'] else 0))
        return self._stage_keyboard(token, panel, text, buttons)

    def _versions_keyboard(self, token, panel, value, *, selected=False):
        entry_id, revision, selector = value
        entry = self.api.Store(self.home).get(entry_id)
        if entry['revision'] != revision or not self._panel_current(token, panel):
            raise ValueError('Delivery changed. Open /shelf again.')
        versions = entry.get('versions') or []
        buttons = []
        if selected:
            version = next(v for v in versions if v['id'] == selector)
            text = f"Shelf · Version {version['number']}\n{entry['title']}"
            for number, item in enumerate(version['files'], 1):
                text += f"\n{number}. {item['name'][:100]} · {item['size']} bytes"
                label = 'Send file' if len(version['files']) == 1 else f"Send {number} · {item['name'][:43]}"
                buttons.append((label, ('download', (entry_id, revision, version['id'], item['id']))))
            if 1 < len(version['files']) <= 5:
                buttons.append(('Send all files', ('download_set', (entry_id, revision, version['id']))))
            buttons.append(('Versions', ('versions', (entry_id, revision, 0))))
        else:
            offset = selector
            text = 'Shelf · Versions\n' + entry['title']
            for version in list(reversed(versions))[offset:offset + PAGE]:
                buttons.append((f"Version {version['number']}", ('version', (entry_id, revision, version['id']))))
            if offset:
                buttons.append(('Previous versions', ('versions', (entry_id, revision, max(0, offset - PAGE)))))
            if offset + PAGE < len(versions):
                buttons.append(('More versions', ('versions', (entry_id, revision, offset + PAGE))))
        buttons.append(('Back to delivery', ('detail', entry_id)))
        return self._stage_keyboard(token, panel, text[:3900], buttons)

    def _version_downloads(self, identity, value):
        if not self.permitted(identity):
            raise ValueError('Not authorized')
        entry_id, revision, version_id = value
        entry = self.api.Store(self.home).get(entry_id)
        if entry['revision'] != revision:
            raise ValueError('Delivery changed')
        version = next(v for v in entry['versions'] if v['id'] == version_id)
        if not 1 <= len(version['files']) <= 5:
            raise ValueError('Choose individual files for versions containing more than five files')
        return [(entry_id, revision, version_id, item['id']) for item in version['files']]

    def _confirm_version(self, token, panel, index):
        self._authorize_panel_commit(token, panel, claim=False)
        refs = list(panel.candidates) if index == -1 else [panel.candidates[index]]
        stamps = [self.api.file_stamp(self.home, self.api.FileRef.model_validate(ref)) for ref in refs]
        self._authorize_panel_commit(token, panel, claim=False)
        panel.version_selection, panel.version_stamps = refs, stamps
        text = ('Shelf · Add version\n' + panel.version_target['title'] +
                '\nThe previous versions will remain available. Save these exact files as a NEW version?\n' +
                '\n'.join(ref['root'] + ':' + ref['path'] for ref in refs))
        return self._stage_keyboard(token, panel, text[:3900], [
            ('Confirm new version', ('commit_version', None)), ('Cancel', ('cancel_recent', None))])

    def _commit_version(self, token, panel):
        from .recent_artifacts import recent, candidates
        old = panel.version_target
        if not old or not panel.version_selection:
            raise ValueError('Choose files before approving a version')
        def authorize():
            self._authorize_panel_commit(token, panel, claim=False)
            current = recent(self.home, self.profile, panel.identity['session_id'], cutoff=panel.delivery.cutoff)
            self._authorize_panel_commit(token, panel, claim=False)
            if current != panel.delivery or candidates(self.api, self.home, current) != panel.candidates:
                raise ValueError('Recent delivery changed. Nothing saved.')
            for ref, stamp in zip(panel.version_selection, panel.version_stamps):
                if self.api.file_stamp(self.home, self.api.FileRef.model_validate(ref)) != stamp:
                    raise ValueError('Selected file changed. Nothing saved.')
            self._authorize_panel_commit(token, panel)
        store = self.api.Store(self.home)
        saved = store.add_version(old['id'], self.api.VersionInput(
            revision=old['revision'], files=panel.version_selection), authorize_commit=authorize)
        verified = store.get(old['id'])
        if (verified != saved or saved['revision'] != old['revision'] + 1 or
                len(saved['versions']) != len(old.get('versions', [])) + 1 or
                any(saved[k] != old[k] for k in ('title', 'tags', 'description', 'kind', 'project', 'session_id'))):
            raise ValueError('Unable to confirm version. Inspect the delivery before retrying.')
        if not self._panel_current(token, panel):
            raise ValueError('Session changed; inspect saved deliveries before retrying')
        panel.consumed = False
        panel.version_target = None
        return self._stage_keyboard(token, panel, 'Shelf · New version saved\n' + saved['title'], [
            ('View saved file', ('detail', saved['id']))])

    def _prepare_send(self, identity, offer, epoch, publication, query):
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            self.prune()
            if self.session_fenced:
                return 'Shelf inline panels unavailable: session-generation guard exhausted or incomplete; restart the owning gateway before using panels.'
            if epoch is not None and epoch != self.epoch:
                return 'Shelf session changed before delivery; request again.'
            if (home != self.home or not self._permitted(identity, owners) or
                    self.application is None or (not offer and not self._publication_current(publication))):
                return 'Shelf inline panels unavailable: configure the Telegram owner policy and use an active session, or use explicit /shelf commands.'
            token = secrets.token_hex(12)
            panel = Panel(identity.copy(), self.generation, time.monotonic() + TTL, offer=offer)
            self.panels[token] = panel
            if publication is not None:
                publication['panel_token'] = token
            application = self.application
        if offer:
            text = 'Shelf · Update available\n' + offer['entry']['title'] + '\n' + offer['file']['path']
            text, markup = self._stage_keyboard(token, panel, text, [
                ('Update registration', ('update', None)), ('Keep current', ('keep', None))])
        else:
            text, markup = self.keyboard(token, panel, query=query, numbered=publication['numeric'])
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

    def _finish_send(self, token, panel, message, epoch, text, publication):
        from telegram import Message
        current = self._panel_current(token, panel, epoch)
        with self.lock:
            if (not current or self.panels.get(token) is not panel or panel.generation != self.generation or
                    panel.expires <= time.monotonic() or (epoch is not None and epoch != self.epoch) or
                    (publication is not None and not self._publication_current(publication))):
                self.panels.pop(token, None)
                return 'Shelf panel expired during delivery; request again.'
            if (not isinstance(message, Message) or not message.is_accessible or
                    str(message.chat.id) != panel.identity['chat'] or str(message.message_thread_id or '') != panel.identity['thread'] or
                    not message.message_id or message.text != text):
                self.panels.pop(token, None)
                return 'Shelf transport returned an unexpected route; panel disabled.'
            panel.message = str(message.message_id)
            panel.actions, panel.pending_actions = panel.pending_actions, {}
            if publication is not None:
                self._publish_results(publication, panel.pending_items)

    def _finish_edit(self, token, panel, message, text, publication):
        from telegram import Message
        current = self._panel_current(token, panel)
        with self.lock:
            if (not current or self.panels.get(token) is not panel or
                    panel.generation != self.generation or panel.expires <= time.monotonic() or
                    not isinstance(message, Message) or not message.is_accessible or
                    str(message.message_id) != panel.message or str(message.chat.id) != panel.identity['chat'] or
                    str(message.message_thread_id or '') != panel.identity['thread'] or message.text != text or
                    (publication is not None and not self._publication_current(publication))):
                self.panels.pop(token, None)
                return False
            panel.actions, panel.pending_actions = panel.pending_actions, {}
            if publication is not None:
                self._publish_results(publication, panel.pending_items)
            return True

    def _drop_panel(self, token):
        with self.lock:
            self.panels.pop(token, None)

    async def send(self, identity, offer=None, epoch=None, query=None):
        from telegram import ReplyParameters
        publication = None if offer else self._begin_publication(identity)
        if not offer and publication is None:
            return 'Shelf · List update in progress or numbered delivery unconfirmed. Use Send file, /shelf r1–r5, or Desktop/Dashboard.'
        token = None
        started = acknowledged = False
        try:
            prepared = await asyncio.to_thread(self._prepare_send, identity, offer, epoch, publication, query)
            if isinstance(prepared, str):
                return prepared
            token, panel, application, text, markup = prepared
            kwargs = dict(chat_id=int(identity['chat']), text=text, reply_markup=markup, parse_mode=None)
            if identity['thread']:
                kwargs['message_thread_id'] = int(identity['thread'])
            if identity['anchor'] and identity['anchor'].isdigit():
                kwargs['reply_parameters'] = ReplyParameters(message_id=int(identity['anchor']), allow_sending_without_reply=False)
            # Memory-only fence after the worker yields back to the loop.
            if publication is not None and not self._publication_current(publication):
                return 'Shelf · List expired. Open /shelf again.'
            started = True
            message = await application.bot.send_message(**kwargs)
            result = await asyncio.to_thread(self._finish_send, token, panel, message, epoch, text, publication)
            acknowledged = result is None
            return result
        except BaseException as exc:
            if token:
                self._drop_panel(token)
            if isinstance(exc, Exception):
                return ('Shelf · List delivery unconfirmed. Numeric downloads disabled; check this chat. '
                        'Use an entry’s Send file or Desktop/Dashboard.' if started else
                        'Shelf · List unavailable or no longer authorized. Try /shelf again.')
            raise
        finally:
            if publication is not None:
                self._end_publication(publication, acknowledged=acknowledged, uncertain=started and not acknowledged)

    @staticmethod
    def _snapshot_key(identity):
        return tuple(identity[k] for k in ('profile', 'user', 'chat', 'thread', 'session_key', 'session_id'))

    def _begin_publication(self, identity):
        """Reserve before any await; overlapping list sends/edits are refused."""
        with self.lock:
            key = self._snapshot_key(identity)
            if key in self.publications or len(self.publications) >= CAPACITY:
                return None
            publication = dict(key=key, epoch=self.epoch, generation=self.generation,
                identity=identity.copy(), expires=time.monotonic() + TTL,
                committed=False, numeric=not self.publication_fenced and key not in self.uncertain_publications)
            self.publications[key] = publication
            self.snapshots.pop(key, None)
            return publication

    def _publication_current(self, publication):
        with self.lock:
            return (publication is not None and self.alive and
                    self.publications.get(publication['key']) is publication and
                    publication['epoch'] == self.epoch and publication['generation'] == self.generation and
                    publication['expires'] > time.monotonic())

    def _publish_results(self, publication, items):
        # Caller checked current owner/home/panel and matching transport receipt.
        with self.lock:
            if not self._publication_current(publication) or items is None:
                return False
            self.snapshots[publication['key']] = dict(identity=publication['identity'].copy(),
                expires=publication['expires'], generation=self.generation, items=list(items))
            publication['committed'] = True
            return True

    def _end_publication(self, publication, *, acknowledged=False, uncertain=False):
        with self.lock:
            key = publication['key']
            if self.publications.get(key) is publication:
                del self.publications[key]
                if uncertain or not publication['committed']:
                    self.snapshots.pop(key, None)
                if not acknowledged and publication.get('panel_token'):
                    self.panels.pop(publication['panel_token'], None)
            if uncertain:
                # An unacknowledged POST may arrive late. A later receipt cannot
                # prove its ordering. Keep a bounded, non-evicting session fence.
                if len(self.uncertain_publications) >= CAPACITY:
                    self.publication_fenced = True
                else:
                    self.uncertain_publications.add(key)

    def numbered_list(self, identity, query):
        if self.api.bound_home() != self.home or not self.permitted(identity):
            return 'Shelf · List unavailable or not authorized.'
        epoch = self.epoch
        if self.application is not None:
            return self.send(identity, epoch=epoch, query=query)
        # The host command contract returns text, not a send receipt. Never
        # advertise or publish numbers from this unacknowledged fallback.
        with self.lock:
            self.snapshots.pop(self._snapshot_key(identity), None)
        data = self.api.Store(self.home).search(q=query, limit=20)
        if (self.api.bound_home() != self.home or not self.permitted(identity) or epoch != self.epoch):
            return 'Shelf · List unavailable or not authorized.'
        lines = [f"Delivery Shelf — {data['total']} matching deliveries"]
        lines.extend(f"• {e['title']}" + ('' if e['file'] else ' · no file attached') for e in data['items'])
        lines.append(NATIVE_UNAVAILABLE)
        lines.append('/shelf search <query> — find a saved delivery\n/shelf help — more options')
        return '\n'.join(lines)

    def select_number(self, identity, number):
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            self.prune()
            snapshot = self.snapshots.get(self._snapshot_key(identity))
            if (home != self.home or not self._permitted(identity, owners) or not snapshot or
                    snapshot['generation'] != self.generation or not 1 <= number <= len(snapshot['items'])):
                return None
            return snapshot['items'][number - 1], snapshot

    def _recent_saved_selection(self, identity, number):
        # rN is an ordinal registration, not a batch size or updated-order list.
        # Keep this bounded query here rather than changing the shared browse order.
        if not self.permitted(identity) or type(number) is not int or not 1 <= number <= 5:
            raise ValueError('Not authorized or invalid saved-entry number')
        store = self.api.Store(self.home)
        if not self.permitted(identity):
            raise ValueError('Session changed')
        with store.connect() as conn:
            row = conn.execute('SELECT id,revision FROM entries ORDER BY created DESC,rowid DESC LIMIT 1 OFFSET ?',
                               (number - 1,)).fetchone()
        if not self.permitted(identity):
            raise ValueError('Session changed')
        return (row['id'], row['revision']) if row else None

    async def download_recent(self, identity, number):
        epoch = self.epoch
        if not await asyncio.to_thread(self.permitted, identity):
            return 'Shelf · File sending unavailable or not authorized.'
        try:
            selection = await asyncio.to_thread(self._recent_saved_selection, identity, number)
        except Exception:
            return 'Shelf · List unavailable. Try /shelf again.'
        if selection is None:
            return f'Shelf · No saved delivery r{number}. Open /shelf to browse.'
        return await self.download(identity, [selection], expected_epoch=epoch)

    async def download_number(self, identity, number):
        epoch = self.epoch
        if self.application is None:
            return 'Shelf · File sending unavailable here. Download in Desktop or Dashboard.'
        selected = await asyncio.to_thread(self.select_number, identity, number)
        if selected is None:
            return 'Shelf · No current numbered result. Open /shelf, then use /shelf dl <number>.'
        selection, snapshot = selected
        return await self.download(identity, [selection], expected_epoch=epoch, snapshot=snapshot)

    @staticmethod
    def _fingerprint(meta):
        return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns,
                meta.st_ctime_ns, meta.st_nlink, meta.st_mode)

    def _file_snapshot(self, selection):
        """Read only through the shared managed-byte/legacy policy boundary."""
        import hashlib
        from types import SimpleNamespace
        store = self.api.Store(self.home)
        entry = store.get(selection[0])
        if entry['revision'] != selection[1]:
            raise ValueError('changed')
        version, file_id = selection[2:] if len(selection) == 4 else (None, None)
        name, content, media_type = self.api.read_entry_file(store, entry, version, file_id)
        if len(content) > self.api.MAX_FILE:
            raise ValueError('unavailable')
        fingerprint = (name, len(content), hashlib.sha256(content).hexdigest(), media_type)
        return entry, SimpleNamespace(path=name), fingerprint, content

    def _download_authorized(self, identity, selection, ref, fingerprint, epoch, application, panel_token, panel, snapshot):
        # Recheck the exact immutable saved version, revision and policy before
        # transport; for legacy entries the helper also rechecks the source policy.
        if not self.permitted(identity):
            return False
        _, _, current, _ = self._file_snapshot(selection)
        if current != fingerprint:
            return False
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            return (home == self.home and epoch == self.epoch and application is self.application and
                    (snapshot is None or (self.snapshots.get(self._snapshot_key(identity)) is snapshot and
                     snapshot['expires'] > time.monotonic() and snapshot['generation'] == self.generation)) and
                    self._permitted(identity, owners) and (panel is None or
                    (self.panels.get(panel_token) is panel and panel.expires > time.monotonic() and
                     panel.busy and panel.generation == self.generation)))

    async def download(self, identity, selections, *, panel_token=None, panel=None, expected_epoch=None, snapshot=None):
        """Native attachments only: no tools, agents, injection, or automatic retry."""
        route = tuple(identity[k] for k in ('profile', 'user', 'chat', 'thread'))
        with self.lock:
            if expected_epoch is not None and expected_epoch != self.epoch:
                return 'Shelf · Session changed. Open /shelf again.'
            if route in self.download_busy:
                return 'Shelf · A file send is already in progress.'
            if self.application is None:
                return 'Shelf · File sending unavailable here. Download in Desktop or Dashboard.'
            self.download_busy.add(route)
            epoch, application = self.epoch, self.application
        sent = unavailable = uncertain = 0
        try:
            for selection in selections[:5]:
                content = None
                try:
                    if not await asyncio.to_thread(self.permitted, identity):
                        unavailable += 1
                        continue
                    entry, ref, fingerprint, content = await asyncio.to_thread(self._file_snapshot, selection)
                    valid = await asyncio.to_thread(self._download_authorized, identity, selection, ref, fingerprint,
                                                    epoch, application, panel_token, panel, snapshot)
                    # No await between this lifecycle fence and entering native transport.
                    with self.lock:
                        valid = (valid and self.alive and epoch == self.epoch and application is self.application and
                                 (snapshot is None or (self.snapshots.get(self._snapshot_key(identity)) is snapshot and
                                  snapshot['expires'] > time.monotonic() and snapshot['generation'] == self.generation)) and
                                 (panel is None or (self.panels.get(panel_token) is panel and panel.busy and
                                  panel.expires > time.monotonic() and panel.generation == self.generation)))
                    if not valid:
                        unavailable += 1
                        del content
                        continue
                    from telegram import InputFile
                    kwargs = dict(chat_id=int(identity['chat']),
                                  document=InputFile(content, filename=ref.path.rsplit('/', 1)[-1]),
                                  disable_content_type_detection=True)
                    if identity['thread']:
                        kwargs['message_thread_id'] = int(identity['thread'])
                    # At most one bounded file resident; maximum batch wire payload 50 MiB.
                    del content
                except Exception:
                    content = None
                    unavailable += 1
                    continue
                try:
                    message = await application.bot.send_document(**kwargs)
                    if (str(message.chat.id) != identity['chat'] or
                            str(message.message_thread_id or '') != identity['thread']):
                        raise ValueError('Unexpected route receipt')
                    sent += 1
                except Exception:
                    uncertain += 1
                    # A failed POST may already have arrived. Never retry it or
                    # continue a batch after an ambiguous transport outcome.
                    break
                finally:
                    del kwargs
            if uncertain:
                remaining = len(selections) - sent - unavailable - uncertain
                return (f'Shelf · {sent} sent; {unavailable} unavailable; {remaining} not attempted. '
                        'Delivery of one file unconfirmed. Check this chat before requesting again.')
            if sent == 1 and len(selections) == 1:
                return 'Shelf · File sent.'
            if not sent and len(selections) == 1:
                return 'Shelf · File unavailable or changed. Open /shelf and select it again.'
            return f'Shelf · {sent} sent; {unavailable} unavailable.'
        finally:
            with self.lock:
                self.download_busy.discard(route)

    def _claim(self, query, application, generation):
        from telegram import Message
        match = re.fullmatch(r'shelf:([a-f0-9]{24}):([0-9]{1,2}|[a-f0-9]{8}|[a-f0-9]{1,16}\.[a-f0-9]{1,2})', query.data if isinstance(query.data, str) else '')
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
                action = panel.actions[match[2]]
                panel.actions, panel.pending_actions = {}, {}
                return match[1], panel, action
        return None

    def _authorize_panel_commit(self, token, panel, *, request=False, claim=True):
        owners, home = self.owners(), self.api.bound_home()
        with self.lock:
            if (self.panels.get(token) is not panel or panel.expires <= time.monotonic() or
                    panel.generation != self.generation or home != self.home or
                    not self._permitted(panel.identity, owners) or not panel.busy or panel.consumed or panel.cancelled.is_set()):
                raise ValueError('Shelf action expired or session changed')
            # Atomic lifecycle/one-shot claim, AFTER write-lock and policy waits.
            # Once authorized, a commit may finish after reset; never pretend rollback.
            if claim:
                panel.consumed = True
            if request:
                return self.new_request(panel.identity)

    def _prepare_text_add(self, identity, raw, epoch, cancelled, loop=None):
        """Native command consent, independent of PTB and metadata inference."""
        # Native RPC proxies inference, but not the caller's cancellation. Local
        # worker flags cannot authorize automatic saves after that caller exits.
        if os.environ.get('HERMES_PLUGIN_HOST_PROCESS') == '1':
            return ('Delivery Shelf not saved: the isolated plugin host cannot propagate caller cancellation. '
                'Open Saved → Delivery Shelf → Add, enter metadata manually (or Generate details to draft), then Save. '
                'No isolation or permission setting needs changing.')
        from .recent_artifacts import recent, candidates, metadata, supplied_metadata, MISSING
        from fastapi import HTTPException
        from pydantic import ValidationError
        import sqlite3
        commit_authorized = False

        def on_commit_authorized():
            nonlocal commit_authorized
            # After final authorization, failure cannot prove a rollback.
            commit_authorized = True

        def failure(detail):
            if commit_authorized:
                return 'Unable to confirm the save. Open Saved → Delivery Shelf to check before retrying.'
            # Source-adapter errors retain their cause without steering an ordinary
            # deterministic command into a model-assisted save.
            detail = str(detail).replace('Ask me to save the file in normal chat.',
                'Open Saved → Delivery Shelf → Add to choose a file from this conversation.')
            return 'Delivery Shelf not saved: ' + detail

        def authorize():
            home = self.api.bound_home()
            if identity['platform'] == 'telegram' and not self.permitted(identity):
                raise ValueError('Authorized current session and Telegram owner policy required.')
            with self.lock:
                if (home != self.home or identity['profile'] != self.profile or not self.alive or
                        self.session_fenced or self.epoch != epoch or cancelled.is_set() or
                        identity['session_id'] in self.retired_sessions):
                    raise ValueError('Conversation or profile changed. Reopen the conversation and use /shelf add again.')

        try:
            authorize()  # Before any source/catalog query, not just before the write.
            if (identity['platform'] not in ('cli', 'desktop', 'tui', 'local', 'api_server', 'telegram') or
                    not isinstance(identity['session_id'], str) or
                    not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', identity['session_id']) or
                    (identity['platform'] != 'cli' and not identity['session_key'])):
                raise ValueError('Current conversation unavailable. Open a conversation and use /shelf add, or choose a file in Saved → Delivery Shelf.')
            from .agent_quick_add import save
            return save(self, identity, raw, authorize, loop,
                        on_commit_authorized=on_commit_authorized)
        except ValidationError:
            return failure('recent file or metadata is unsupported by the current policy.')
        except HTTPException as exc:
            return failure(exc.detail)
        except ValueError as exc:
            return failure(exc)
        except (OSError, sqlite3.Error):
            return 'Unable to confirm the save. Open Saved → Delivery Shelf to check before retrying.'

    async def add_recent_text(self, identity, raw='', epoch=None):
        cancelled = threading.Event()
        try:
            return await asyncio.to_thread(self._prepare_text_add, identity, raw, epoch, cancelled, asyncio.get_running_loop())
        except asyncio.CancelledError:
            cancelled.set()  # Cancellation does not stop a worker waiting for SQLite.
            raise

    def _load_recent(self, token, panel):
        from .recent_artifacts import recent, candidates, metadata, MISSING
        self._authorize_panel_commit(token, panel, claim=False)
        delivery = recent(self.home, self.profile, panel.identity['session_id'], count=panel.recent_count)
        self._authorize_panel_commit(token, panel, claim=False)
        if delivery is None:
            raise ValueError(MISSING)
        refs = candidates(self.api, self.home, delivery)
        self._authorize_panel_commit(token, panel, claim=False)
        # Validate explicit fields before offering or committing any choice.
        for ref in refs:
            metadata(self.api, ref, panel.identity['session_id'], panel.supplied)
        panel.delivery, panel.candidates = delivery, refs


    def _choose_recent(self, token, panel):
        from pathlib import Path
        names = [Path(ref['path']).name for ref in panel.candidates]
        labels = [ref['path'] if names.count(names[i]) > 1 else names[i]
                  for i, ref in enumerate(panel.candidates)]
        # Number long/colliding labels so truncation cannot make choices identical.
        labels = [label if len(label) <= 60 and labels.count(label) == 1 else f'{i+1}. …{label[-53:]}'
                  for i, label in enumerate(labels)]
        choices = [(label, ('save_recent', i)) for i, label in enumerate(labels)]
        if panel.version_target:
            choices.append(('Use all recent files', ('save_recent', -1)))
        elif len(panel.candidates) > 1:
            choices.append((f'Save all {len(panel.candidates)} files', ('save_recent', -1)))
        return self._stage_keyboard(token, panel, 'Shelf · Choose a file to save',
            choices + [('Cancel', ('cancel_recent', -1))])


    def _recent_metadata(self, token, panel, ref):
        """One bounded configured-model call, no agent injection or tool loop."""
        from .recent_artifacts import metadata, generation_request
        self._authorize_panel_commit(token, panel, claim=False)
        entry = metadata(self.api, ref, panel.identity['session_id'], panel.supplied)
        missing = [key for key in ('title', 'tags', 'description') if key not in panel.supplied]
        stamp = self.api.file_stamp(self.home, self.api.FileRef.model_validate(ref))
        if missing:
            if self.loop is None or not self.loop.is_running():
                raise ValueError('Metadata generation unavailable. Supply title, #tags and --description explicitly.')
            request = generation_request(self.api, panel.delivery, ref, panel.identity['session_id'])
            async def generate():
                if not await asyncio.to_thread(self._panel_current, token, panel):
                    raise ValueError('Shelf session changed before metadata generation')
                return await self.api.generate_draft(request, self.api.Store(self.home))
            future = asyncio.run_coroutine_threadsafe(generate(), self.loop)
            try:
                result = future.result(timeout=self.api.GENERATION_TIMEOUT + 5)
            except BaseException:
                future.cancel()
                raise
            self._authorize_panel_commit(token, panel, claim=False)
            # Presence, not truthiness: even a deliberately empty description wins.
            entry = self.api.EntryInput.model_validate(entry.model_dump() | {
                key: result['draft'][key] for key in missing})
        if stamp != self.api.file_stamp(self.home, self.api.FileRef.model_validate(ref)):
            raise ValueError('File changed during metadata generation. Nothing saved.')
        self._authorize_panel_commit(token, panel, claim=False)
        return entry, stamp

    def _save_recent(self, token, panel, index):
        from .recent_artifacts import recent, candidates
        from pathlib import Path
        refs = list(panel.candidates) if index == -1 else [panel.candidates[index]]
        # MAX_FILES caps this loop at eight independent structured calls. A
        # failure in any draft aborts before the single copied-byte transaction.
        drafts = [self._recent_metadata(token, panel, ref) for ref in refs]
        entry = drafts[0][0]
        if len(refs) > 1:
            payload = entry.model_dump() | {'files': refs, 'file': refs[0]}
            if 'title' not in panel.supplied:
                suffix = f' (+{len(refs)-1} files)'
                payload['title'] = entry.title[:160-len(suffix)] + suffix
            if 'description' not in panel.supplied:
                payload['description'] = '\n'.join(
                    Path(ref['path']).name + ': ' + draft.description
                    for ref, (draft, _) in zip(refs, drafts))[:4000]
            if 'tags' not in panel.supplied:
                payload['tags'] = list(dict.fromkeys(tag for draft, _ in drafts for tag in draft.tags))[:20]
            entry = self.api.EntryInput.model_validate(payload)
        def authorize():
            # Called after the catalog write reservation and current file-policy check.
            # Revalidate the read boundary first: a SQLite wait may outlive the
            # bound profile, owner, session or task. Do not consume until reads finish.
            self._authorize_panel_commit(token, panel, claim=False)
            current = recent(self.home, self.profile, panel.identity['session_id'], cutoff=panel.delivery.cutoff,
                             count=panel.recent_count)
            self._authorize_panel_commit(token, panel, claim=False)
            if current != panel.delivery or candidates(self.api, self.home, current) != panel.candidates:
                raise ValueError('Recent delivery changed. Use /shelf add again.')
            for ref, (_, stamp) in zip(refs, drafts):
                if stamp != self.api.file_stamp(self.home, self.api.FileRef.model_validate(ref)):
                    raise ValueError('File changed before save. Nothing saved.')
            self._authorize_panel_commit(token, panel)
        saved, existing = self.api.Store(self.home).register_file_once(entry, authorize_commit=authorize)
        if not self._panel_current(token, panel):
            raise ValueError('Session changed; inspect saved deliveries before retrying')
        # Drop all old save callbacks, but leave a read-only detail action available.
        with self.lock:
            panel.consumed = False
        if existing and saved.get('files', [saved['file']]) != refs:
            text = ('The primary file is already saved with a different file set. Nothing overwritten. '
                    'View saved file → Add version to approve a new version.')
        else:
            text = ('Already saved to Delivery Shelf: ' if existing else 'Saved to Delivery Shelf: ') + saved['title']
        return self._stage_keyboard(token, panel, text, [('View saved file', ('detail', saved['id']))])


    def _prepare_recent(self, identity, raw, epoch, cancelled):
        from .recent_artifacts import supplied_metadata
        from fastapi import HTTPException
        from pydantic import ValidationError
        try:
            if not self.permitted(identity) or self.api.bound_home() != self.home:
                return 'Delivery Shelf not saved: authorized current session and Telegram owner policy required.'
            if self.application is None:
                return NATIVE_UNAVAILABLE
            count = None
            selector = re.match(r'^r([0-9]+)(?:\s|$)', raw)
            if selector:
                if not re.fullmatch(r'[1-8]', selector[1]):
                    raise ValueError('Use /shelf add r1 through r8. Nothing saved.')
                count, raw = int(selector[1]), raw[selector.end():].strip()
            supplied = supplied_metadata(raw)
            with self.lock:
                if self.epoch != epoch:
                    return 'Shelf session changed. Use /shelf add again.'
                self.prune()
                token = secrets.token_hex(12)
                panel = Panel(identity.copy(), self.generation, time.monotonic()+TTL, busy=True,
                              supplied=supplied, cancelled=cancelled, recent_count=count)
                self.panels[token] = panel
            try:
                self._load_recent(token, panel)
                if not self._panel_current(token, panel, epoch):
                    raise ValueError('Shelf session changed. Use /shelf add again.')
                if count is not None or len(panel.candidates) == 1:
                    text, markup = self._save_recent(token, panel, -1 if count is not None else 0)
                elif self.application is None:
                    raise ValueError('Several recent files found. Nothing saved. Open Saved → Delivery Shelf → Add and choose the file from this conversation.')
                else:
                    text, markup = self._choose_recent(token, panel)
                panel.busy = False
                return token, panel, self.application, text, markup
            except BaseException:
                self._drop_panel(token)
                raise
        except ValidationError:
            return 'Delivery Shelf not saved: recent file or metadata is unsupported by the current policy.'
        except HTTPException as exc:
            return 'Delivery Shelf not saved: ' + str(exc.detail)
        except ValueError as exc:
            return str(exc)
        except (OSError, TimeoutError, __import__('sqlite3').Error):
            return 'Shelf · Unable to confirm save. Inspect /shelf before retrying; storage or generation failed.'


    async def add_recent(self, identity, raw='', epoch=None):
        # Quick command capture is text-only; the host owns its one-line reply.
        # The panel's Add action below remains the deliberate chooser workflow.
        if not await asyncio.to_thread(self.permitted, identity):
            return 'Delivery Shelf not saved: authorized current session and Telegram owner policy required.'
        if self.application is None:
            return NATIVE_UNAVAILABLE
        return await self.add_recent_text(identity, raw, epoch)

    async def _add_recent_panel(self, identity, raw='', epoch=None):
        cancelled = threading.Event()
        try:
            prepared = await asyncio.to_thread(self._prepare_recent, identity, raw, epoch, cancelled)
        except asyncio.CancelledError:
            cancelled.set()  # A cancelled to_thread worker may still be waiting for SQLite.
            raise
        if isinstance(prepared, str):
            return prepared
        token, panel, application, text, markup = prepared
        if application is None:
            self._drop_panel(token)
            return text
        kwargs = dict(chat_id=int(identity['chat']), text=text, reply_markup=markup, parse_mode=None)
        if identity['thread']:
            kwargs['message_thread_id'] = int(identity['thread'])
        try:
            if not await asyncio.to_thread(self._panel_current, token, panel, epoch):
                return 'Shelf session changed; inspect saved deliveries before retrying.'
            with self.lock:
                if (self.panels.get(token) is not panel or not self.alive or
                        self.epoch != epoch or panel.expires <= time.monotonic() or panel.cancelled.is_set()):
                    return 'Shelf session changed; inspect saved deliveries before retrying.'
            message = await application.bot.send_message(**kwargs)
            return await asyncio.to_thread(self._finish_send, token, panel, message, epoch, text, None)
        except BaseException:
            await asyncio.to_thread(self._drop_panel, token)
            raise


    def _perform(self, token, panel, action, value, publication=None):
        if not self._panel_current(token, panel):
            return None
        if action in ('versions', 'version'):
            return self._versions_keyboard(token, panel, value, selected=action == 'version')
        if action == 'add_version':
            entry = self.api.Store(self.home).get(value[0])
            if entry['revision'] != value[1]:
                raise ValueError('Delivery changed. Open /shelf again.')
            panel.version_target = entry
            panel.recent_count = None  # A new button action is not the old rN command.
            panel.version_selection, panel.version_stamps = [], []
            self._load_recent(token, panel)
            return (self._choose_recent(token, panel) if len(panel.candidates) > 1 else
                    self._confirm_version(token, panel, 0))
        if action == 'commit_version':
            return self._commit_version(token, panel)
        if action in ('add', 'save_recent'):
            from fastapi import HTTPException
            from pydantic import ValidationError
            try:
                if action == 'add':
                    panel.version_target = None
                    panel.recent_count = None
                    panel.supplied = {}  # A new Add action is a fresh metadata request.
                    try:
                        self._load_recent(token, panel)
                    except ValidationError:
                        return 'Delivery Shelf not saved: recent file or metadata is unsupported by the current policy.', None
                    except ValueError as exc:
                        return str(exc), None
                    if not self._panel_current(token, panel):
                        return None
                    if len(panel.candidates) > 1:
                        return self._choose_recent(token, panel)
                if panel.version_target:
                    return self._confirm_version(token, panel, value)
                return self._save_recent(token, panel, 0 if action == 'add' else value)
            except (ValueError, HTTPException, ValidationError):
                # No automatic retry; source/policy may have changed or readback may be ambiguous.
                self._drop_panel(token)
                return 'Shelf · Unable to confirm save\nUse /shelf to inspect saved files, or ask me to save the file in normal chat.', None
        if action == 'cancel_recent':
            self._authorize_panel_commit(token, panel)
            return 'Shelf · Cancelled\nNothing saved.', None
        if action in ('page', 'detail'):
            if action == 'page':
                if publication is None or not self._publication_current(publication):
                    return None
                result = self.keyboard(token, panel, offset=value, numbered=publication['numeric'])
            else:
                result = self.keyboard(token, panel, detail=value)
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
                    verified[k] != old[k] for k in self.api.EntryInput.model_fields if k not in ('file', 'files')):
                raise ValueError('Readback changed; inspect the registration before retrying')
            if not self._panel_current(token, panel):
                raise ValueError('Session changed; inspect the registration before retrying')
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
        publication = self._begin_publication(panel.identity) if action == 'page' else None
        started = acknowledged = False
        try:
            if action == 'page' and publication is None:
                await query.answer('Shelf list update in progress. Try again.', show_alert=True)
                return
            await query.answer('Sending file…' if action in ('download', 'download_set') else None)
            if action in ('download', 'download_set'):
                # Claim the specific action once, including ambiguous POST outcomes.
                with self.lock:
                    panel.actions = {k: v for k, v in panel.actions.items() if v != (action, value)}
                selections = (await asyncio.to_thread(self._version_downloads, panel.identity, value)
                              if action == 'download_set' else [value])
                result = await self.download(panel.identity, selections, panel_token=token, panel=panel)
                await query.edit_message_text(text=result, reply_markup=None, parse_mode=None)
                return
            result = await asyncio.to_thread(self._perform, token, panel, action, value, publication)
            if result is not None:
                text, markup = result
                if publication is not None and not self._publication_current(publication):
                    return
                if markup is not None:
                    if not await asyncio.to_thread(self._panel_current, token, panel):
                        return
                    with self.lock:
                        if (self.panels.get(token) is not panel or not self.alive or
                                panel.expires <= time.monotonic() or panel.generation != self.generation):
                            return
                started = True
                message = await query.edit_message_text(text=text, reply_markup=markup, parse_mode=None)
                acknowledged = await asyncio.to_thread(self._finish_edit, token, panel, message, text, publication)
        except asyncio.CancelledError:
            # Cancelling to_thread does not stop its worker. Fence it before
            # releasing busy so a waiting write cannot authorize after cancellation.
            await asyncio.to_thread(self._drop_panel, token)
            raise
        except Exception:
            # A commit may have succeeded before transport/readback failed; never claim rollback.
            # Retire old and staged Add/download actions before the error edit.
            self._drop_panel(token)
            try:
                text = ('Shelf · File delivery unconfirmed. Check this chat before requesting again.' if action == 'download' else
                        'Shelf · Could not complete confirmation\nRefresh and inspect the registration before retrying; it may have changed.')
                await query.edit_message_text(text=text, reply_markup=None, parse_mode=None)
            except Exception:
                pass
        finally:
            if publication is not None:
                self._end_publication(publication, acknowledged=acknowledged, uncertain=started and not acknowledged)
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
