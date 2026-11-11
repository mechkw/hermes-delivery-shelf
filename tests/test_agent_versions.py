"""Exact native tools, real SQLite and managed bytes; no transport/modal mocks."""
import asyncio
import json
from test_agent_awareness import AgentAwareNativeTests


class VersionContractTests(AgentAwareNativeTests):
    async def saved(self, *names):
        self.deliver(*(names or ('first.md',)))
        await self.command()
        return self.store.search()['items'][0]

    def offer(self, item, name='second.md', body='New version'):
        (self.home/'workspaces'/name).write_text(body)
        self.deliver(name)
        return self.tool('delivery_shelf_offer_update', {'id':item['id'], 'file':{'root':'workspaces','path':name}})

    def respond(self, offer, decision='yes', **kwargs):
        return self.tool('delivery_shelf_respond_update', {'offer_id':offer['offer_id'],'decision':decision}, **kwargs)

    async def test_unchanged_duplicate_and_same_path_changed_bytes(self):
        item = await self.saved()
        self.deliver('first.md')
        same = self.tool('delivery_shelf_offer_update', {'id':item['id'],'file':item['file']})
        self.assertEqual(same['status'], 'unchanged')
        self.assertFalse(same['notify_user'])
        offer = self.offer(item, 'first.md', 'Changed SAME PATH')
        self.assertEqual(offer['status'], 'offered', offer)
        self.assertEqual(self.store.get(item['id']), item)
        result = self.respond(offer)
        self.assertTrue(result['ok'], result)
        updated = self.store.get(item['id'])
        self.assertEqual(len(updated['versions']), 2)
        self.assertEqual(self.api.read_entry_file(self.store, updated)[1], b'Changed SAME PATH')
        self.assertEqual(updated['versions'][0], item['versions'][0])

    async def test_always_scoped_entry_persists_reload_and_pauses_archive_trash(self):
        item = await self.saved()
        result = self.respond(self.offer(item), 'always')
        self.assertTrue(result['ok'], result)
        await asyncio.to_thread(self.manager.discover_and_load, force=True)
        self.controller = self.manager.get_platform_handler_factories('telegram')[0][0].__self__
        other = self.store.create(self.api.EntryInput(title='Other deliberately saved', file=self.api.FileRef(root='workspaces',path='first.md'),session_id='native-current'))
        self.assertEqual(self.offer(other, 'first.md', 'Other changed')['status'], 'offered')
        automatic = self.offer(item, 'second.md', 'Third bytes')
        self.assertEqual(automatic['status'], 'saved', automatic)
        for state in ('archive','trash'):
            self.store.bulk_action({'action':state,'ids':[item['id']]})
            before = self.store.get(item['id'])
            paused = self.offer(item, 'second.md', state+' new bytes')
            self.assertEqual(paused['status'], 'paused', paused)
            self.assertEqual(self.store.get(item['id']), before)
            self.store.bulk_action({'action':'restore','ids':[item['id']]})
        self.assertEqual(self.offer(item, 'second.md', 'After restore')['status'], 'saved')

    async def test_companion_set_and_managed_bytes_preserved_without_original(self):
        item = await self.saved('first.md','second.md')
        offered = self.offer(item, 'first.md', 'Changed primary')
        result = self.respond(offered)
        self.assertTrue(result['ok'], result)
        updated = self.store.get(item['id'])
        self.assertEqual(updated['files'], item['files'])
        self.assertEqual(updated['versions'][-1]['files'][1]['sha256'], item['versions'][0]['files'][1]['sha256'])
        (self.home/'workspaces/second.md').unlink()
        accepted = self.respond(self.offer(updated, 'first.md', 'Another primary'))
        self.assertTrue(accepted['ok'], accepted)
        latest = self.store.get(item['id'])
        self.assertEqual(latest['files'], item['files'])
        self.assertEqual(latest['versions'][-1]['files'][1]['provenance'], item['versions'][0]['files'][1]['provenance'])
        self.assertEqual(latest['versions'][-1]['files'][1]['sha256'], item['versions'][0]['files'][1]['sha256'])

    async def test_multifile_new_path_requires_exact_member_and_preserves_companion(self):
        item = await self.saved('first.md','second.md')
        ambiguous = self.offer(item, 'new.md', 'A named derivative')
        self.assertFalse(ambiguous['ok'], ambiguous)
        self.assertIn('replaces', ambiguous['error'])
        self.assertEqual(self.store.get(item['id']), item)
        args = {'id':item['id'],'file':{'root':'workspaces','path':'new.md'},'replaces':item['files'][1]}
        offered = self.tool('delivery_shelf_offer_update', args)
        self.assertEqual(offered['replaces'], item['files'][1])
        self.assertTrue(self.respond(offered)['ok'])
        updated = self.store.get(item['id'])
        self.assertEqual(updated['files'], [item['files'][0], args['file']])
        self.assertEqual(updated['versions'][-1]['files'][0]['sha256'], item['versions'][0]['files'][0]['sha256'])

    async def test_keep_expired_and_unregistered_offers_never_first_capture(self):
        item = await self.saved()
        offered = self.offer(item)
        self.assertEqual(self.respond(offered, 'keep')['status'], 'kept')
        self.assertFalse(self.respond(offered)['ok'])
        offered = self.offer(item, body='Another version')
        with self.controller.awareness.connect() as conn:
            conn.execute('UPDATE version_offers SET expires=0 WHERE token=?',(offered['offer_id'],))
        self.assertFalse(self.respond(offered)['ok'])
        unknown = self.tool('delivery_shelf_offer_update', {'id':'a'*32,'file':{'root':'workspaces','path':'second.md'}})
        self.assertFalse(unknown['ok'])
        self.assertEqual(self.store.get(item['id']), item)
        self.assertEqual(self.store.search()['total'], 1)

    async def test_offer_cross_session_stale_bytes_reset_and_revision_guards(self):
        item = await self.saved()
        offered = self.offer(item)
        self.db.create_session('other',source='desktop')
        self.assertFalse(self.respond(offered, session_id='other')['ok'])
        (self.home/'workspaces/second.md').write_text('Changed after offer')
        self.assertFalse(self.respond(offered)['ok'])
        self.assertEqual(self.store.get(item['id']), item)
        offered = self.offer(item, body='Fresh offer')
        self.store.update(item['id'], self.api.EntryUpdate(title='Edited',revision=1))
        self.assertFalse(self.respond(offered)['ok'])
        offered = self.offer(self.store.get(item['id']), body='Newest offer')
        self.manager.invoke_hook('on_session_reset',old_session_id='native-current',session_id='replacement')
        self.assertFalse(self.respond(offered)['ok'])
        self.assertEqual(len(self.store.get(item['id'])['versions']), 1)

    async def test_manual_ui_save_context_and_verified_compaction_parent(self):
        item = self.store.create(self.api.EntryInput(title='Manual UI save',file=self.api.FileRef(root='workspaces',path='first.md'),session_id='native-current'))
        self.db.create_session('compressed', source='desktop',parent_session_id='native-current')
        result = self.manager.invoke_hook('pre_llm_call',session_id='compressed',parent_session_id='native-current')
        self.assertIn(item['id'], result[0]['context'])
        await asyncio.to_thread(self.manager.discover_and_load, force=True)
        result = self.manager.invoke_hook('pre_llm_call',session_id='compressed')
        self.assertIn(item['id'], result[0]['context'])
        self.db.create_session('unrelated', source='desktop')
        self.assertEqual(self.manager.invoke_hook('pre_llm_call',session_id='unrelated',parent_session_id='native-current'), [])

    async def test_cleanup_worker_runs_without_ui_and_stops_unload(self):
        item = await self.saved()
        self.store.bulk_action({'action':'trash','ids':[item['id']]})
        with self.store.connect() as conn:
            conn.execute('UPDATE entry_lifecycle SET delete_after=0 WHERE entry_id=?',(item['id'],))
        self.controller.cleanup_stop.set()
        self.controller.cleanup_thread.join(timeout=2)
        self.controller.start_cleanup(interval=.01)
        for _ in range(100):
            if self.store.search(state='all')['total'] == 0:
                break
            await asyncio.sleep(.01)
        self.assertEqual(self.store.search(state='all')['total'], 0)
        self.assertTrue((self.home/'workspaces/first.md').exists())
        worker = self.controller.cleanup_thread
        self.manager.unload()
        self.assertFalse(worker.is_alive())
