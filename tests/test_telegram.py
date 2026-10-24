"""Offline PTB capture tests: no tokens, network, live gateway or model calls."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(os.environ.get('HERMES_SOURCE', Path.home()/'.hermes/hermes-agent'))))
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from gateway.session_context import set_session_vars, clear_session_vars
from hermes_cli.plugin_command_dispatch import invoke_plugin_command
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes
from telegram.request import BaseRequest

spec = importlib.util.spec_from_file_location('shelf_telegram_plugin', ROOT/'__init__.py')
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class Capture(BaseRequest):
    def __init__(self):
        self.calls = []
        self.serial = 100
        self.fail = set()
    @property
    def read_timeout(self): return 1
    async def initialize(self): pass
    async def shutdown(self): pass
    async def do_request(self, url, method, request_data=None, **kwargs):
        verb = url.rsplit('/', 1)[-1]
        data = request_data.parameters if request_data else {}
        self.calls.append((verb, data))
        if verb in self.fail:
            return 400, json.dumps({'ok': False, 'description': 'Fictional transport rejection'}).encode()
        if verb == 'getMe':
            result = {'id': 909, 'is_bot': True, 'first_name': 'Fixture', 'username': 'fixture_bot'}
        elif verb in ('sendMessage', 'editMessageText'):
            self.serial += 1
            result = {'message_id': data.get('message_id', self.serial), 'date': 1,
                      'chat': {'id': data['chat_id'], 'type': 'private'}, 'text': data['text']}
            if data.get('message_thread_id'): result['message_thread_id'] = data['message_thread_id']
            if data.get('reply_markup'): result['reply_markup'] = data['reply_markup']
        else: result = True
        return 200, json.dumps({'ok': True, 'result': result}).encode()


class Context:
    profile_name = 'default'
    def __init__(self):
        self.tools, self.commands, self.hooks, self.prompts = {}, {}, {}, {}
        self.queued = []
        self.accept = True
    def register_tool(self, **kwargs): self.tools[kwargs['name']] = kwargs['handler']
    def register_command(self, name, handler, **kwargs): self.commands[name] = handler
    def register_hook(self, name, handler): self.hooks[name] = handler
    def register_system_prompt_section(self, name, content): self.prompts[name] = content
    def on_unload(self, callback): self.cleanup = callback
    def register_platform_handler(self, platform, factory): self.factory = factory
    def inject_message(self, content, **kwargs):
        self.queued.append((content, kwargs))
        return self.accept


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shelf-ptb-', dir=os.environ.get('TMPDIR'))
        self.home = Path(self.tmp.name)/'home'
        (self.home/'workspaces').mkdir(parents=True)
        for name in ('old.md', 'new.md', 'third.md'):
            (self.home/'workspaces'/name).write_text('Fictional output')
        self.token = set_hermes_home_override(self.home)
        self.ctx = Context()
        plugin.register(self.ctx)
        self.controller = self.ctx.factory.__self__
        self.policy = self.home/'plugin-data/delivery-shelf/telegram-owners.json'
        self.policy.parent.mkdir(parents=True, exist_ok=True)
        self.policy.write_text('["17"]')
        self.capture = Capture()
        self.app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(self.capture).updater(None).build()
        await self.app.initialize()
        self.ctx.factory(self.app, object())
        self.source = SimpleNamespace(user_id='17', chat_id='17', thread_id='9', message_id='22')
        self.identity = self.controller.identity(self.source, 'fictional-session', 'telegram:17:9', 'telegram')
        self.store = plugin._service().Store(self.home)
        self.entry = self.store.create(plugin._service().EntryInput(
            title='Fictional report', description='Preserve this description', tags=['Keep-Case'],
            kind='report', project='Fiction', session_id='original-session',
            file={'root':'workspaces', 'path':'old.md'}))

    async def asyncTearDown(self):
        self.ctx.cleanup()
        await self.app.shutdown()
        clear_session_vars([])
        reset_hermes_home_override(self.token)
        self.tmp.cleanup()

    @contextmanager
    def session(self, **changes):
        values = dict(platform='telegram', user_id='17', chat_id='17', thread_id='9',
                      message_id='22', session_key='telegram:17:9', session_id='fictional-session', profile='default')
        values.update(changes)
        tokens = set_session_vars(**values)
        try: yield
        finally: clear_session_vars(tokens)

    async def panel(self, session_id='fictional-session'):
        response = invoke_plugin_command(self.ctx.commands['shelf'], '', source=self.source,
                                         session_id=session_id, session_key='telegram:17:9', platform='telegram')
        self.assertIsNone(await response)
        return next(reversed(self.controller.panels))

    def sent(self): return [d for v,d in self.capture.calls if v == 'sendMessage']
    def edited(self): return [d for v,d in self.capture.calls if v == 'editMessageText']

    async def click(self, token, key='0', *, user=17, chat=17, thread=9, message=None, data=None, app=None, date=1):
        panel = self.controller.panels.get(token)
        message_id = message if message is not None else int(panel.message if panel else self.capture.serial)
        update = Update.de_json({'update_id': 1, 'callback_query': {
            'id':'fictional-query', 'from':{'id':user,'is_bot':False,'first_name':'Fixture'},
            'chat_instance':'fixture', 'data':data or f'shelf:{token}:{key}',
            'message':{'message_id':message_id, 'date':date, 'message_thread_id':thread,
                       'chat':{'id':chat,'type':'private'}, 'text':'Shelf'}}}, self.app.bot)
        selected = app or self.app
        # Exercise PTB's registered handler selection and callback, not a fabricated callback object.
        await selected.process_update(update)

    async def offer(self, path='new.md', session_id='fictional-session'):
        with self.session(session_id=session_id):
            result = await asyncio.to_thread(self.ctx.tools['delivery_shelf_offer_update'],
                                            {'id':self.entry['id'], 'file':{'root':'workspaces','path':path}})
        return json.loads(result)

    async def test_actual_markup_order_topic_details_and_paging(self):
        for i in range(7): self.store.create(plugin._service().EntryInput(title=f'Fixture {i}'))
        token = await self.panel()
        data = self.sent()[-1]
        markup = InlineKeyboardMarkup.de_json(data['reply_markup'], self.app.bot)
        self.assertTrue(all(len(row) == 1 for row in markup.inline_keyboard))
        self.assertEqual(markup.inline_keyboard[0][0].text, 'Add')
        self.assertEqual(markup.inline_keyboard[-1][0].text, 'Browse more')
        self.assertEqual(data['message_thread_id'], 9)
        self.assertEqual(data['reply_parameters']['message_id'], 22)
        self.assertLessEqual(max(len(row[0].callback_data.encode()) for row in markup.inline_keyboard), 64)
        await self.click(token, '1')
        self.assertIn('Details', self.edited()[-1]['text'])
        await self.click(token, '1')  # back
        await self.click(token, '6')  # browse more
        self.assertIn('Previous', str(self.edited()[-1]['reply_markup']))
        self.assertNotIn('ReplyKeyboard', str(self.sent()))

    async def test_add_queue_register_search_readback_and_replay(self):
        token = await self.panel()
        await self.click(token)
        self.assertEqual(self.store.search()['total'], 1)
        self.assertIn('Nothing saved yet', self.edited()[-1]['text'])
        prompt, destination = self.ctx.queued[-1]
        payload = json.loads(prompt.split('\n', 1)[1])
        self.assertEqual(destination['session_key'], 'telegram:17:9')
        self.assertIn('no filesystem scans', prompt)
        args = dict(title='Newest current-context artifact', file={'root':'workspaces','path':'new.md'},
                    session_id='fictional-session', request_id=payload['request_id'])
        with self.session():
            saved = json.loads(self.ctx.tools['delivery_shelf_register'](args))
            self.assertTrue(saved['ok'], saved)
            found = json.loads(self.ctx.tools['delivery_shelf_search']({'q':'Newest'}))
            self.assertEqual(found['data']['items'][0], saved['data'])
            self.assertFalse(json.loads(self.ctx.tools['delivery_shelf_register'](args))['ok'])
        await self.click(token)
        self.assertEqual(len(self.ctx.queued), 1)

    async def test_callback_boundaries_and_namespace(self):
        token = await self.panel()
        for changes in ({'user':18}, {'chat':18}, {'thread':10}, {'message':999}, {'date':0},
                        {'data':'shelf:../../bad:0'}, {'data':f'shelf:{token}:99'}, {'data':'mp:foreign'}):
            await self.click(token, **changes)
        self.assertEqual(self.ctx.queued, [])
        self.policy.write_text('[]')
        await self.click(token)
        self.assertEqual(self.ctx.queued, [])
        self.policy.write_text('["17"]')
        self.controller.panels[token].expires = 0
        await self.click(token)
        self.assertEqual(self.ctx.queued, [])

    async def test_reset_before_click_and_delayed_register_denied(self):
        token = await self.panel()
        await self.click(token)
        request = json.loads(self.ctx.queued[-1][0].split('\n',1)[1])['request_id']
        self.ctx.hooks['on_session_reset'](old_session_id='fictional-session', session_id='new-session')
        args = dict(title='Stale', session_id='fictional-session', request_id=request,
                    file={'root':'workspaces','path':'new.md'})
        with self.session(session_id='new-session'):
            self.assertFalse(json.loads(self.ctx.tools['delivery_shelf_register'](args))['ok'])
            args.pop('request_id')
            self.assertFalse(json.loads(self.ctx.tools['delivery_shelf_register'](args))['ok'])
        self.assertEqual(self.store.search()['total'], 1)
        token = await self.panel(session_id='new-session')
        self.ctx.hooks['on_session_delete'](session_id='new-session')
        await self.click(token)
        self.assertEqual(len(self.ctx.queued), 1)

    async def test_injection_denial_and_missing_owner_policy(self):
        self.ctx.accept = False
        token = await self.panel()
        await self.click(token)
        self.assertIn('not saved', self.edited()[-1]['text'])
        self.assertEqual(self.controller.requests, {})
        self.policy.unlink()
        before = len(self.sent())
        result = await self.controller.send(self.identity)
        self.assertIn('unavailable', result)
        self.assertEqual(len(self.sent()), before)

    async def test_same_file_silent_and_new_offer_keep_then_update(self):
        (self.home/'workspaces/old.md').write_text('Edited same file')
        self.assertEqual((await self.offer('old.md'))['status'], 'same_file_silent')
        self.assertEqual(self.sent(), [])
        offered = await self.offer()
        self.assertEqual(offered['status'], 'offered')
        self.assertFalse(offered['saved'])
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        self.assertEqual((await self.offer())['status'], 'already_offered')
        token = next(reversed(self.controller.panels))
        self.assertEqual([r[0]['text'] for r in self.sent()[-1]['reply_markup']['inline_keyboard']],
                         ['Update registration','Keep current'])
        await self.click(token, '1')
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        self.assertEqual((await self.offer('third.md'))['status'], 'offered')
        token = next(reversed(self.controller.panels))
        await self.click(token)
        saved = self.store.get(self.entry['id'])
        self.assertEqual(saved['file']['path'], 'third.md')
        self.assertEqual(saved['revision'], 2)
        for key in ('id','title','description','tags','kind','project','session_id','created'):
            self.assertEqual(saved[key], self.entry[key])
        await self.click(token)
        self.assertEqual(self.store.get(self.entry['id']), saved)
        self.assertEqual(self.store.search()['total'], 1)
        self.assertIn('Updated', self.edited()[-1]['text'])

    async def test_cas_conflict_and_file_policy_revocation(self):
        await self.offer()
        token = next(reversed(self.controller.panels))
        payload = {k:self.entry[k] for k in plugin._service().EntryInput.model_fields}
        revised = self.store.update(self.entry['id'], plugin._service().EntryUpdate(**payload, revision=1))
        await self.click(token)
        self.assertEqual(self.store.get(self.entry['id']), revised)
        self.assertNotIn('Updated', self.edited()[-1]['text'])
        await self.offer('third.md')
        token = next(reversed(self.controller.panels))
        (self.policy.parent/'allowed-roots.json').write_text('{}')
        await self.click(token)
        self.assertEqual(self.store.get(self.entry['id']), revised)

    async def test_invalid_derivatives_cli_fallback_and_profile(self):
        for path in ('missing.md','../escape.md','.secret.md','credentials.md'):
            self.assertFalse((await self.offer(path))['ok'])
        args = {'id':self.entry['id'], 'file':{'root':'workspaces','path':'new.md'}}
        with self.session(platform='cli'):
            result = json.loads(await asyncio.to_thread(self.ctx.tools['delivery_shelf_offer_update'], args))
        self.assertEqual(result['status'], 'unsupported')
        with self.session(profile='other'):
            self.assertFalse(json.loads(await asyncio.to_thread(self.ctx.tools['delivery_shelf_offer_update'], args))['ok'])
        self.assertEqual(self.sent(), [])

    async def test_unload_reconnect_and_bounded_state(self):
        token = await self.panel()
        await self.offer()
        self.ctx.factory(self.app, object())
        self.assertEqual(self.controller.panels, {})
        await self.click(token)
        self.assertEqual(self.ctx.queued, [])
        # Reconnect uses a NEW Application in production; old callbacks are fenced.
        self.ctx.cleanup()
        self.assertIn('unavailable', await self.controller.send(self.identity))
        self.assertEqual(self.store.get(self.entry['id']), self.entry)
        for _ in range(300): self.controller.new_request(self.identity)
        self.assertLessEqual(len(self.controller.requests), 128)

    async def test_parallel_double_click_and_reset_during_ack(self):
        token = await self.panel()
        await asyncio.gather(self.click(token), self.click(token))
        self.assertEqual(len(self.ctx.queued), 1)
        token = await self.panel()
        original = self.capture.do_request
        async def reset_at_ack(url, method, **kwargs):
            if url.endswith('/answerCallbackQuery'):
                self.ctx.hooks['on_session_reset'](old_session_id='fictional-session', session_id='replacement')
            return await original(url, method, **kwargs)
        self.capture.do_request = reset_at_ack
        await self.click(token)
        self.assertEqual(len(self.ctx.queued), 1)
        self.assertEqual(self.controller.requests, {})

    async def test_profile_session_and_application_separation(self):
        token = await self.panel()
        await self.click(token)
        request = json.loads(self.ctx.queued[-1][0].split('\n', 1)[1])['request_id']
        args = dict(title='Wrong scope', session_id='fictional-session', request_id=request,
                    file={'root':'workspaces','path':'new.md'})
        for changed in ({'session_key':'telegram:17:10'}, {'user_id':'18'}, {'chat_id':'18'},
                        {'thread_id':'10'}, {'profile':'other'}):
            with self.session(**changed):
                self.assertFalse(json.loads(self.ctx.tools['delivery_shelf_register'](args))['ok'])
        other = Path(self.tmp.name)/'profiles/other'
        other.mkdir(parents=True)
        bound = set_hermes_home_override(other)
        try:
            second_ctx = Context()
            second_ctx.profile_name = 'other'
            plugin.register(second_ctx)
            second = second_ctx.factory.__self__
            self.assertNotEqual(second.home, self.controller.home)
            with self.session(profile='other'):
                self.assertFalse(json.loads(second_ctx.tools['delivery_shelf_register'](args))['ok'])
            self.assertIn('unavailable', await self.controller.send(
                self.controller.identity(self.source,'fictional-session','telegram:17:9','telegram')))
            self.assertEqual(plugin._service().Store(other).search()['total'], 0)
            second_ctx.cleanup()
        finally:
            reset_hermes_home_override(bound)
        capture = Capture()
        other_app = Application.builder().token('456789:FICTIONAL_TEST_TOKEN').request(capture).updater(None).build()
        await other_app.initialize()
        try:
            token = await self.panel()
            old_handler = self.app.handlers[0][0]
            # Even leaked callback bytes cannot move an action to another bot Application.
            other_app.add_handler(old_handler)
            await self.click(token, app=other_app)
            self.assertEqual(len(self.ctx.queued), 1)
            self.ctx.factory(other_app, object())
            await self.click(token)  # old Application/client generation fenced
            self.assertEqual(len(self.ctx.queued), 1)
        finally:
            await other_app.shutdown()

    async def test_alias_same_path_silence_and_offer_owner_revocation(self):
        (self.policy.parent/'allowed-roots.json').write_text(json.dumps({
            'workspaces':str(self.home/'workspaces'), 'alias':str(self.home/'workspaces')}))
        with self.session():
            result = json.loads(await asyncio.to_thread(self.ctx.tools['delivery_shelf_offer_update'],
                {'id':self.entry['id'],'file':{'root':'alias','path':'old.md'}}))
        self.assertEqual(result['status'], 'same_file_silent')
        self.assertEqual(self.sent(), [])
        await self.offer()
        token = next(reversed(self.controller.panels))
        self.policy.write_text('[]')
        await self.click(token)
        self.assertEqual(self.store.get(self.entry['id']), self.entry)

    async def test_delayed_send_epoch_and_postcommit_transport_failure(self):
        epoch = self.controller.epoch
        self.ctx.hooks['on_session_reset'](old_session_id='fictional-session', session_id='replacement')
        self.assertIn('changed', await self.controller.send(self.identity, epoch=epoch))
        self.assertEqual(self.sent(), [])
        self.assertFalse((await self.offer())['ok'])  # pinned old agent cannot offer after reset
        await self.offer(session_id='replacement')
        token = next(reversed(self.controller.panels))
        self.capture.fail.add('editMessageText')
        await self.click(token)
        self.assertEqual(self.store.get(self.entry['id'])['file']['path'], 'new.md')
        self.assertTrue(self.controller.panels[token].consumed)
        # Transport failed after commit: no rollback claim, and double-click cannot commit again.
        await self.click(token)
        self.assertEqual(self.store.get(self.entry['id'])['revision'], 2)

    async def test_retired_generation_capacity_fails_closed(self):
        for i in range(130):
            self.ctx.hooks['on_session_reset'](old_session_id=f'old-{i}', session_id=f'new-{i}')
        self.assertLessEqual(len(self.controller.retired_sessions), 128)
        self.assertTrue(self.controller.session_fenced)
        self.assertIn('unavailable', await self.controller.send(self.identity))
        self.assertFalse((await self.offer())['ok'])
        self.assertEqual(self.sent(), [])

    async def test_transport_failure_never_reports_offer(self):
        self.capture.fail.add('sendMessage')
        self.assertFalse((await self.offer())['ok'])
        self.assertEqual(self.controller.panels, {})
        self.assertEqual(self.store.get(self.entry['id']), self.entry)


if __name__ == '__main__': unittest.main()
