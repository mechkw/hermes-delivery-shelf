"""Official loader + gateway dispatcher + PTB capture; all homes fictional."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(os.environ.get('HERMES_SOURCE', Path.home()/'.hermes/hermes-agent'))))
from test_telegram import Capture
from telegram import Update
from telegram.ext import Application
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager
from hermes_state import SessionDB
from hermes_cli.plugin_command_dispatch import invoke_plugin_command
from gateway.run_inbound_hooks import GatewayInboundHooksMixin
from gateway.session import SessionSource
from gateway.config import GatewayConfig, Platform
from gateway.session_context import set_session_vars, clear_session_vars
from tools.registry import registry


class Runner(GatewayInboundHooksMixin):
    config = GatewayConfig()
    def _session_key_for_source(self, source): return 'telegram:17:9'
    @contextmanager
    def _session_env_scope(self, context):
        tokens = set_session_vars(platform='telegram', session_key=context.session_key,
                                  session_id=context.session_id, user_id='17', chat_id='17',
                                  thread_id='9', message_id='22', profile=self.profile)
        try: yield
        finally: clear_session_vars(tokens)
    async def _run_in_executor_with_context(self, call): return await asyncio.to_thread(call)


def prepare(home, isolation='in_process'):
    target = home/'plugins/delivery-shelf'
    target.mkdir(parents=True)
    for name in ('__init__.py','telegram_shelf.py','recent_artifacts.py','agent_awareness.py','agent_quick_add.py','agent_versions.py','plugin.yaml'):
        shutil.copy2(ROOT/name, target/name)
    shutil.copytree(ROOT/'dashboard',target/'dashboard')
    (home/'workspaces').mkdir()
    for name in ('first.md','second.md'):
        (home/'workspaces'/name).write_text('Fictional native-loader output')
    (home/'plugin-data/delivery-shelf').mkdir(parents=True)
    (home/'plugin-data/delivery-shelf/telegram-owners.json').write_text('["17"]')
    (home/'config.yaml').write_text('plugins:\n  enabled: [delivery-shelf]\n  isolation: '+isolation+'\n  entries:\n    delivery-shelf:\n      allow_gateway_injection: true\n')


async def main():
    with tempfile.TemporaryDirectory(prefix='shelf-native-ptb-', dir=os.environ.get('TMPDIR')) as directory:
        home = Path(directory)/'home'
        prepare(home)
        token = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        app = db = None
        try:
            await asyncio.to_thread(manager.discover_and_load)
            info = [p for p in manager.list_plugins() if p['name']=='delivery-shelf']
            assert len(info)==1 and not info[0]['error'], info
            factory, name = manager.get_platform_handler_factories('telegram')[0]
            controller = factory.__self__
            capture = Capture()
            app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(capture).updater(None).build()
            await app.initialize()
            factory(app, object())
            handler = manager._plugin_commands['shelf']['handler']  # inspect the actual loader's registered value
            now = datetime.now(timezone.utc)
            entry = SimpleNamespace(session_key='telegram:17:9', session_id='native-session', created_at=now, updated_at=now)
            source = SessionSource(platform=Platform.TELEGRAM, chat_id='17', chat_type='dm', user_id='17', thread_id='9')
            source.message_id = '22'
            runner = Runner()
            runner.profile = controller.profile
            result = await runner._hm_run_plugin_handler(handler, None, source, session_entry=entry, args='')
            assert result is None, result
            panel = next(iter(controller.panels.values()))
            nonce = next(iter(controller.panels))
            assert capture.calls[-1][1]['reply_markup']['inline_keyboard'][0][0]['text']=='Add'
            queued = []
            owner = object()
            manager.set_gateway_message_injector(owner, lambda **payload: queued.append(payload) or True)
            def update(data):
                return Update.de_json({'update_id':1, 'callback_query':{
                    'id':'fixture-callback','from':{'id':17,'is_bot':False,'first_name':'Fixture'},
                    'chat_instance':'fixture', 'data':data,
                    'message':{'message_id':int(panel.message),'date':1,'message_thread_id':9,
                               'chat':{'id':17,'type':'private'},'text':'Shelf'}}},app.bot)
            assert await runner._hm_run_plugin_handler(handler, None, source, session_entry=entry,
                args='add --file workspaces:first.md') is None
            assert len(queued)==1 and queued[0]['session_key']=='telegram:17:9', queued
            assert Path(queued[0]['plugin_home'])==home
            search = registry.get_entry('delivery_shelf_search',scope=manager.scope_key).handler
            register = registry.get_entry('delivery_shelf_register',scope=manager.scope_key).handler
            offer = registry.get_entry('delivery_shelf_offer_update',scope=manager.scope_key).handler
            respond = registry.get_entry('delivery_shelf_respond_update',scope=manager.scope_key).handler
            assert json.loads(search({}))['data']['total']==0
            request = json.loads(queued[0]['content'].split('\n',1)[1])['supplied']['request_id']
            with runner._session_env_scope(entry):
                saved = json.loads(register({'title':'Native result','tags':['Keep-Case'],
                    'description':'Fictional description','session_id':'native-session','request_id':request,
                    'file':{'root':'workspaces','path':'first.md'}}))
                assert saved['ok'], saved
                readback = json.loads(search({}))['data']['items'][0]
                assert readback==saved['data']
                unavailable = json.loads(await asyncio.to_thread(offer, {'id':readback['id'],
                    'file':{'root':'workspaces','path':'second.md'}}))
                assert unavailable['ok'] is False and json.loads(search({}))['data']['items']==[readback]
                # A concrete version needs a completed delivery in this exact session.
                (home/'workspaces/second.md').write_text('Fictional newly delivered native revision')
                db = SessionDB(home/'state.db')
                db.create_session('native-session', source='telegram', user_id='17')
                delivered = db.append_message('native-session', 'assistant',
                    'MEDIA:'+str(home/'workspaces/second.md'))
                offered = json.loads(await asyncio.to_thread(offer, {'id':readback['id'],
                    'file':{'root':'workspaces','path':'second.md'}}))
                assert offered['ok'] and offered['status']=='offered' and offered['saved'] is False, offered
                assert offered['id']==readback['id'] and offered['file']['path']=='second.md'
                assert json.loads(search({}))['data']['items']==[readback]
            # Stage a native confirmation before conversational approval. The
            # successful version must fence this separate revision-1 callback.
            assert await runner._hm_run_plugin_handler(handler, None, source, session_entry=entry, args='') is None
            nonce = next(reversed(controller.panels))
            panel = controller.panels[nonce]
            async def click_label(label):
                markup = capture.calls[-1][1]['reply_markup']['inline_keyboard']
                data = next(b['callback_data'] for row in markup for b in row if b['text']==label)
                await app.process_update(update(data))
                return data
            await click_label('Native result')
            await click_label('Add version')
            with runner._session_env_scope(entry):
                approved = json.loads(await asyncio.to_thread(respond,
                    {'offer_id':offered['offer_id'], 'decision':'yes'}))
                assert approved['ok'] and approved['saved'], approved
            await click_label('Confirm new version')
            assert 'Could not complete confirmation' in capture.calls[-1][1]['text']
            final = json.loads(search({}))['data']['items'][0]
            assert final['id']==readback['id'] and final['file']['path']=='second.md' and final['revision']==2
            assert final['tags']==['Keep-Case'] and final['description']=='Fictional description'
            assert final==approved['data'] and final['versions'][0]==readback['versions'][0]
            assert final['versions'][-1]['files'][0]['provenance']['message_id']==delivered
            result = await runner._hm_run_plugin_handler(handler, None, source, session_entry=entry,
                args='add NativeCase #Keep-Tag --file workspaces:first.md')
            assert result is None and len(queued) == 2
            supplied = json.loads(queued[-1]['content'].split('\n',1)[1])['supplied']
            assert supplied['request_id'] != request
            with runner._session_env_scope(entry):
                second = json.loads(await asyncio.to_thread(register, {**supplied, 'description':'Explicit follow-up'}))
            assert second['ok'], second
            assert json.loads(search({'q':'NativeCase'}))['data']['items'][0] == second['data']
            assert second['data']['tags'] == ['Keep-Tag']
            group = SessionSource(platform=Platform.TELEGRAM, chat_id='-100', chat_type='group', user_id='17', thread_id='9')
            refusal = await runner._hm_run_plugin_handler(handler, None, group, session_entry=entry, args='add --file workspaces:first.md')
            assert 'Nothing queued' in refusal and len(queued) == 2
            print('PASS native completed Add → fresh explicit-file token → exact readback; shared-group refusal before native injection')
            manager.invoke_hook('on_session_reset', old_session_id='native-session', session_id='new-session')
            assert not controller.panels and not controller.requests
            manager.clear_gateway_message_injector(owner)
            print('PASS official loader → real gateway sync/awaitable dispatcher → PTB Application/InlineKeyboardMarkup capture')
            print('PASS native consent injection queued; exact readback; offered ≠ saved; approved same-ID version with provenance; stale callback CAS; native reset hook')
            assert manager.unload('delivery-shelf')
            assert not controller.alive
        finally:
            manager.unload()
            if app: await app.shutdown()
            if db: db.close()
            reset_hermes_home_override(token)

        # Real out-of-process host, never an isolation mock. Native transport stays absent.
        home = Path(directory)/'isolated'
        prepare(home, 'host')
        token = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        try:
            await asyncio.to_thread(manager.discover_and_load)
            info = [p for p in manager.list_plugins() if p['name']=='delivery-shelf']
            assert len(info)==1 and not info[0]['error'], info
            assert not manager.get_platform_handler_factories('telegram')
            handler = manager._plugin_commands['shelf']['handler']
            result = await asyncio.to_thread(invoke_plugin_command, handler, '', platform='telegram')
            assert 'Delivery Shelf' in result and '/shelf search <query>' in result, result
            assert 'Inline panels unavailable' not in result and '--file' not in result
            for args in ('dl 1', 'download 1', 'r3'):
                fallback = await asyncio.to_thread(invoke_plugin_command, handler, args, platform='telegram')
                assert isinstance(fallback, str) and 'not bound on this gateway' in fallback, fallback
                assert 'Nothing saved or sent' in fallback and 'keep isolation unchanged' in fallback
            print('PASS real isolated plugin host: loads text command, no native factories, honest inline fallback')
        finally:
            manager.unload()
            reset_hermes_home_override(token)


if __name__=='__main__': asyncio.run(main())
