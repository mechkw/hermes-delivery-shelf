"""Official loader/dispatcher/PTB forum attachments; rejecting inference seams."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from native_telegram import prepare, Runner
from test_telegram import Capture
from telegram import Update
from telegram.ext import Application
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugins import PluginManager
from gateway.session import SessionSource
from gateway.config import Platform


async def main():
    with tempfile.TemporaryDirectory(prefix='shelf-download-native-', dir=os.environ.get('TMPDIR')) as directory:
        home = Path(directory)/'home'
        prepare(home)
        # Retrieval is independent of agent handoff permission.
        config = home/'config.yaml'
        config.write_text(config.read_text().replace('allow_gateway_injection: true', 'allow_gateway_injection: false'))
        token = set_hermes_home_override(home)
        manager = PluginManager(str(home))
        capture = Capture()
        app = Application.builder().token('123456:FICTIONAL_TEST_TOKEN').request(capture).updater(None).build()
        try:
            await asyncio.to_thread(manager.discover_and_load)
            factory, _ = manager.get_platform_handler_factories('telegram')[0]
            controller = factory.__self__
            await app.initialize()
            factory(app, object())
            api = controller.api
            payload = b'PK\x03\x04fictional opaque ZIP bytes\x00\xff'
            (home/'workspaces/bundle.zip').write_bytes(payload)
            store = api.Store(home)
            saved = store.create(api.EntryInput(title='Native archive', description='Fixture', tags=['Native'],
                file={'root':'workspaces','path':'bundle.zip'}))
            baseline = store.search()
            sentinel = home/'history-sentinel'
            sentinel.write_bytes(b'No session or bookmark mutation')
            before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
            source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100', chat_type='group', user_id='17', thread_id='9')
            source.message_id = '22'
            now = datetime.now(timezone.utc)
            entry = SimpleNamespace(session_key='telegram:-100:9', session_id='native-download', created_at=now, updated_at=now)
            runner = Runner()
            runner.profile = controller.profile
            handler = manager._plugin_commands['shelf']['handler']
            async def command(args):
                return await runner._hm_run_plugin_handler(handler, None, source, session_entry=entry, args=args)
            reject = Mock(side_effect=AssertionError('No model/tool handoff permitted'))
            with patch.object(controller.ctx, 'inject_message', reject), patch.object(type(controller.ctx), 'llm', property(lambda self: reject())), patch('zipfile.ZipFile', reject):
                assert await command('') is None
                nonce = next(iter(controller.panels))
                panel = controller.panels[nonce]
                def update(data, user=17, topic=9):
                    return Update.de_json({'update_id':1,'callback_query':{
                        'id':'fixture','from':{'id':user,'is_bot':False,'first_name':'Fixture'},
                        'chat_instance':'fixture','data':data,
                        'message':{'message_id':int(panel.message),'date':1,'message_thread_id':topic,
                        'chat':{'id':-100,'type':'supergroup','is_forum':True},'text':'Shelf'}}}, app.bot)
                await app.process_update(update(f'shelf:{nonce}:1'))
                last = [d for v,d in capture.calls if v=='editMessageText'][-1]
                send = next(r[0]['callback_data'] for r in last['reply_markup']['inline_keyboard'] if r[0]['text']=='Send file')
                await app.process_update(update(send, user=18))
                await app.process_update(update(send, topic=10))
                assert not capture.uploads
                await app.process_update(update(send))
                await app.process_update(update(send))
                assert len(capture.uploads)==1
                assert await command('search Native') is None
                assert '1. Native archive' in [d for v,d in capture.calls if v=='sendMessage'][-1]['text']
                assert 'sent' in await command('dl 1')
                assert 'sent' in await command('download 1')
                assert '2 fewer attached' in await command('r3')
                assert len(capture.uploads)==4
                for verb, data, files in capture.uploads:
                    assert verb=='sendDocument' and data['chat_id']==-100 and data['message_thread_id']==9
                    assert data['disable_content_type_detection'] is True
                    assert files['document'][0]=='bundle.zip' and files['document'][1]==payload
                # Reproduce P1A through the official dispatcher and PTB transport:
                # old number 1 was acknowledged; the newer list is rejected.
                assert await command('search Native') is None
                (home/'workspaces/unseen.md').write_bytes(b'Unseen native bytes')
                store.create(api.EntryInput(title='Unseen native report',
                    file={'root':'workspaces','path':'unseen.md'}))
                baseline = store.search()
                capture.fail.add('sendMessage')
                assert 'unconfirmed' in await command('')
                capture.fail.clear()
                assert 'Open /shelf' in await command('dl 1')
                assert len(capture.uploads)==4
                # P1B: no captured-profile query or title/count disclosure.
                foreign = home/'profiles/foreign'
                foreign.mkdir(parents=True)
                foreign_token = set_hermes_home_override(foreign)
                try:
                    with patch.object(api.Store, 'search', side_effect=AssertionError('Foreign query')) as search:
                        denied = await command('search Native')
                        assert 'Native' not in denied and 'matching deliveries' not in denied
                        search.assert_not_called()
                finally:
                    reset_hermes_home_override(foreign_token)
                reject.assert_not_called()
            assert store.search()==baseline and store.get(saved['id'])==saved
            assert hashlib.sha256(sentinel.read_bytes()).hexdigest()==before
            assert not (home/'state.db').exists()
            assert not (home/'plugin-data/conversation-bookmarks').exists()
            print(json.dumps({'result':'PASS','native_loader':True,'gateway_dispatcher':True,
                'ptb_forum_uploads':len(capture.uploads),'exact_bytes':True,'inference_calls':reject.call_count,
                'commands':['/shelf','Send file','/shelf search Native','/shelf dl 1','/shelf download 1','/shelf r3'],
                'metadata_unchanged':True,'history_bookmarks_unchanged':True,'live_telegram':False}))
        finally:
            manager.unload()
            await app.shutdown()
            reset_hermes_home_override(token)

if __name__=='__main__': asyncio.run(main())
