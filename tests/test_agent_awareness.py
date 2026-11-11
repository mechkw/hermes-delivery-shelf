"""Native registrations for bounded durable context and conversational version consent."""
import asyncio
import json
from unittest.mock import patch
from test_agent_quick_add import QuickAddNativeTests
from tools.registry import registry


class AgentAwareNativeTests(QuickAddNativeTests):
    def tool(self, name, args, session_id='native-current'):
        entry = registry.get_entry(name, scope=self.manager.scope_key)
        self.assertIsNotNone(entry, name)
        return json.loads(entry.handler(args, session_id=session_id))

    async def test_known_save_context_survives_reload_and_deduplicates_revision(self):
        self.deliver('first.md')
        await self.command()
        saved = self.store.search()['items'][0]
        def context(history=None):
            return self.manager.invoke_hook('pre_llm_call', session_id='native-current',
                conversation_history=history or [], user_message='Revise the report.')
        result = context()
        self.assertEqual(len(result), 1)
        text = result[0]['context']
        self.assertIn(saved['id'], text)
        self.assertIn('first.md', text)
        self.assertLess(len(text), 3000)
        self.assertEqual(context([{'role':'user','content':text}]), [])
        await asyncio.to_thread(self.manager.discover_and_load, force=True)
        self.assertIn(saved['id'], context()[0]['context'])
        self.db.create_session('unrelated', source='desktop')
        self.assertEqual(self.manager.invoke_hook('pre_llm_call', session_id='unrelated'), [])

    async def test_offer_then_yes_adds_exact_version_without_retitling_or_modal(self):
        self.deliver('first.md')
        await self.command()
        saved = self.store.search()['items'][0]
        (self.home/'workspaces/second.md').write_text('Second version bytes')
        row = self.deliver('second.md')
        offered = self.tool('delivery_shelf_offer_update', {'id':saved['id'],
            'file':{'root':'workspaces','path':'second.md'}})
        self.assertTrue(offered['ok'], offered)
        self.assertEqual(offered['status'], 'offered')
        self.assertEqual(self.store.get(saved['id']), saved)
        accepted = self.tool('delivery_shelf_respond_update', {'offer_id':offered['offer_id'], 'decision':'yes'})
        self.assertTrue(accepted['ok'], accepted)
        updated = self.store.get(saved['id'])
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['title'], saved['title'])
        self.assertEqual(updated['files'], [{'root':'workspaces','path':'second.md'}])
        self.assertEqual(len(updated['versions']), 2)
        self.assertFalse(self.tool('delivery_shelf_respond_update', {'offer_id':offered['offer_id'], 'decision':'yes'})['ok'])
        self.assertEqual(self.controller.panels, {})
