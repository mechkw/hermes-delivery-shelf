"""Review regressions at ASGI endpoints, with the actual native SessionDB schema."""
import json
import sqlite3
import threading
import unittest
from contextlib import contextmanager, closing
from pathlib import Path
from fastapi.testclient import TestClient
from hermes_state import SessionDB
from types import SimpleNamespace
from unittest.mock import patch
import test_desktop_sources as fixtures
api = fixtures.api


@contextmanager
def database(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        yield conn


class DesktopReview(unittest.TestCase):
    home: Path
    file: Path
    anchor: int
    client: TestClient
    db: SessionDB
    setUp = fixtures.DesktopSources.setUp

    def capture_model(self):
        calls = []
        async def complete(**kw):
            calls.append(kw)
            return SimpleNamespace(parsed={'title': 'Reviewed', 'description': '', 'tags': []})
        api.bind_generation(SimpleNamespace(llm=SimpleNamespace(acomplete_structured=complete), on_unload=self.addCleanup))
        return calls

    def selected(self, sid='fictional'):
        return self.client.get(f'/sources/sessions/{sid}/artifacts').json()['items'][0]

    def test_source_change_between_resolution_and_collection_never_reaches_model(self):
        selected = self.selected()
        calls = self.capture_model()
        artifacts = api.source_module('artifact_source')
        original = artifacts.resolve
        resolved, mutated = threading.Event(), threading.Event()
        def writer():
            if not resolved.wait(5):
                return
            with database(self.home/'state.db') as conn:
                conn.execute('UPDATE messages SET content=? WHERE id=?',
                             ('PRIVATE REPLACEMENT\nMEDIA:'+str(self.file), self.anchor))
            mutated.set()
        worker = threading.Thread(target=writer)
        worker.start()
        def barrier(*args, **kw):
            result = original(*args, **kw)
            resolved.set()
            self.assertTrue(mutated.wait(5))
            return result
        with patch.object(artifacts, 'resolve', side_effect=barrier):
            result = self.client.post('/generation/draft', json={'session_id':'fictional', 'source':selected['source']})
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(calls, [], 'Replacement body must never be sent, even if final response is 409')
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    def test_private_metadata_is_denied_by_discovery_resolution_and_registration(self):
        selected = self.selected()
        calls = self.capture_model()
        metadata_cases = [json.dumps({key: True}) for key in ('hidden', 'synthetic', 'model_only', 'reasoning', 'thought')]
        metadata_cases += [json.dumps({'channel': channel}) for channel in ('analysis', 'reasoning', 'thought', 'unknown')]
        metadata_cases += ['', '{', '[]', 'null', 'false', '{"model_only":true,"model_only":false}', '{"hidden":NaN}']
        for metadata in metadata_cases:
            with self.subTest(metadata=metadata):
                with database(self.home/'state.db') as conn:
                    conn.execute('UPDATE messages SET display_metadata=? WHERE id=?', (metadata, self.anchor))
                listed = self.client.get('/sources/sessions/fictional/artifacts')
                saved = self.client.post('/sources/register', json={'title':'No leak', 'session_id':'fictional', 'file':selected['file'], 'source':selected['source']})
                generated = self.client.post('/generation/draft', json={'session_id':'fictional', 'source':selected['source']})
                self.assertEqual(listed.status_code, 200, listed.text)
                self.assertEqual(listed.json()['items'], [], metadata)
                self.assertNotIn('field-notes', listed.text)
                self.assertEqual(saved.status_code, 409, saved.text)
                self.assertIn(generated.status_code, (409, 422), generated.text)
        self.assertEqual(calls, [])
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    def test_delegate_and_inherited_delegate_are_denied_at_every_endpoint(self):
        calls = self.capture_model()
        for variant in ('direct', 'compression-child', 'fork-child'):
            with self.subTest(variant=variant):
                sid = 'delegate-'+variant
                self.db.create_session(sid, source='desktop')
                self.db.set_session_title(sid, 'PRIVATE DELEGATE TITLE '+variant)
                self.db.append_message(sid, 'user', 'Delegate-only request')
                self.db.append_message(sid, 'assistant', 'MEDIA:'+str(self.file))
                selected = self.selected(sid)
                if variant != 'direct':
                    parent = sid+'-parent'
                    self.db.create_session(parent, source='desktop')
                    with database(self.home/'state.db') as conn:
                        conn.execute('UPDATE sessions SET model_config=?,end_reason=? WHERE id=?',
                                     (json.dumps({'_delegate_from':'fictional'}), 'compression', parent))
                        config = {'_branched_from':parent} if variant == 'fork-child' else {}
                        conn.execute('UPDATE sessions SET model_config=?,parent_session_id=? WHERE id=?', (json.dumps(config), parent, sid))
                else:
                    with database(self.home/'state.db') as conn:
                        conn.execute('UPDATE sessions SET model_config=? WHERE id=?', (json.dumps({'_delegate_from':'fictional'}), sid))
                listed = self.client.get('/sources/sessions')
                artifacts = self.client.get(f'/sources/sessions/{sid}/artifacts')
                saved = self.client.post('/sources/register', json={'title':'No', 'session_id':sid, 'file':selected['file'], 'source':selected['source']})
                generated = self.client.post('/generation/draft', json={'session_id':sid, 'source':selected['source']})
                self.assertNotIn('PRIVATE DELEGATE TITLE', listed.text)
                self.assertNotIn(sid, [r['id'] for r in listed.json()['items']])
                for response in (artifacts, saved, generated):
                    self.assertIn(response.status_code, (404, 422), response.text)
                    self.assertNotIn('field-notes', response.text)
        self.assertEqual(calls, [])
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    def test_automation_does_not_consume_eligible_conversation_window(self):
        for n in range(1005):
            sid = f'automation-{n}'
            self.db.create_session(sid, source='cron' if n % 2 else 'automation')
            self.db.set_session_title(sid, f'PRIVATE AUTOMATION TITLE {n}')
        listed = self.client.get('/sources/sessions')
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([r['id'] for r in listed.json()['items']], ['fictional'])
        self.assertFalse(listed.json()['window']['truncated'])
        self.assertNotIn('PRIVATE AUTOMATION TITLE', listed.text)
        self.assertEqual(self.client.get('/sources/sessions/automation-0/artifacts').status_code, 404)

    def test_request_context_is_immutable_across_other_window_and_simultaneous_preference_writes(self):
        self.db.create_session('long', source='desktop')
        for n in range(55):
            self.db.append_message('long', 'user', f'History request {n}')
            self.db.append_message('long', 'assistant', f'History answer {n}')
        self.db.append_message('long', 'user', 'Focal request')
        self.db.append_message('long', 'assistant', 'MEDIA:'+str(self.file))
        self.db.append_message('long', 'user', 'FUTURE MUST NOT LEAK')
        selected = self.selected('long')
        calls = self.capture_model()
        # A has already loaded 10; B persists 50 before A clicks Generate.
        self.assertEqual(self.client.get('/generation/settings').json()['previous_exchanges'], 10)
        self.client.put('/generation/settings', json={'previous_exchanges':50})
        body = {'session_id':'long', 'source':selected['source'], 'previous_exchanges':10}
        result = self.client.post('/generation/draft', json=body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['context']['requested_exchanges'], 10)
        self.assertEqual(result.json()['context']['previous_exchanges'], 10)
        original = api.generation_payload
        entered, changed = threading.Event(), threading.Event()
        def writer():
            if entered.wait(5):
                self.client.put('/generation/settings', json={'previous_exchanges':20})
                changed.set()
        worker = threading.Thread(target=writer)
        worker.start()
        def barrier(*args):
            entered.set()
            self.assertTrue(changed.wait(5))
            return original(*args)
        with patch.object(api, 'generation_payload', side_effect=barrier):
            result = self.client.post('/generation/draft', json=body)
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['context']['previous_exchanges'], 10)
        for call in calls:
            wire = json.dumps(call)
            self.assertIn('History request 45', wire)
            self.assertNotIn('History request 44', wire)
            self.assertNotIn('FUTURE', wire)
        self.assertEqual(len(calls), 2)
        for value in (True, '10', 10.0, 0, -1, 17, 51, None):
            self.assertEqual(self.client.post('/generation/draft', json={**body, 'previous_exchanges':value}).status_code, 422)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.client.get('/generation/settings').json()['previous_exchanges'], 20)
        self.assertEqual(self.client.get('/entries').json()['total'], 0)

    def test_native_compression_child_missing_delegate_marker_is_denied(self):
        self.db.create_session('native-parent', source='desktop', model_config={'_delegate_from':'fictional'})
        self.db.append_message('native-parent', 'user', 'PRIVATE delegated request')
        self.db.append_message('native-parent', 'assistant', 'MEDIA:'+str(self.file))
        history = self.db.get_messages_as_conversation('native-parent')
        self.db.publish_compression_child(parent_session_id='native-parent', child_session_id='native-child',
            source='desktop', messages=history, require_compression_lease=False)
        with database(self.home/'state.db') as conn:
            conn.execute("UPDATE sessions SET model_config='{}' WHERE id='native-child'")
            anchor, body = conn.execute("SELECT id,content FROM messages WHERE session_id='native-child' AND role='assistant' ORDER BY id DESC LIMIT 1").fetchone()
        import hashlib
        ref = {'root':'workspaces', 'path':'field-notes.md'}
        digest = hashlib.sha256(body.encode()).hexdigest()
        origin = {'message_id':anchor, 'digest':digest, 'artifact_id':hashlib.sha256(json.dumps(['native-child',anchor,digest,ref], sort_keys=True).encode()).hexdigest()}
        calls = self.capture_model()
        self.assertNotIn('native-child', [r['id'] for r in self.client.get('/sources/sessions').json()['items']])
        self.assertEqual(self.client.get('/sources/sessions/native-child/artifacts').status_code, 422)
        self.assertEqual(self.client.post('/sources/register', json={'title':'No', 'file':ref, 'session_id':'native-child', 'source':origin}).status_code, 422)
        self.assertEqual(self.client.post('/generation/draft', json={'session_id':'native-child', 'source':origin, 'previous_exchanges':10}).status_code, 422)
        self.assertEqual(calls, [])

    def test_legacy_carried_anchor_never_hydrates_future_bodies(self):
        from contextlib import contextmanager
        self.db.create_session('legacy', source='desktop')
        self.db.append_message('legacy', 'user', 'First request', timestamp=100)
        self.db.append_message('legacy', 'assistant', 'First answer', timestamp=99)
        self.db.append_message('legacy', 'user', 'Selected request', timestamp=98)
        anchor = self.db.append_message('legacy', 'assistant', 'MEDIA:'+str(self.file), timestamp=97)
        future = [self.db.append_message('legacy', 'user', 'FUTURE request', timestamp=1),
                  self.db.append_message('legacy', 'assistant', 'FUTURE answer', timestamp=2)]
        with database(self.home/'state.db') as conn:
            conn.execute('''INSERT INTO messages(session_id,role,content,timestamp,active)
                SELECT session_id,role,content,timestamp,active FROM messages WHERE id=?''', (anchor,))
            conn.execute("UPDATE messages SET display_identity=NULL,display_order=NULL WHERE session_id='legacy'")
        selected = self.selected('legacy')
        self.assertGreater(selected['source']['message_id'], max(future))
        calls = self.capture_model()
        history = api.source_module('native_history')
        original, queries = history.SourceAdapter.chooser_connection, []
        @contextmanager
        def trace(source):
            with original(source) as conn:
                conn.set_trace_callback(queries.append)
                yield conn
        with database(self.home/'state.db') as conn:
            before = list(conn.iterdump())
        with patch.object(history.SourceAdapter, 'chooser_connection', trace):
            result = self.client.post('/generation/draft', json={'session_id':'legacy', 'source':selected['source'], 'previous_exchanges':10})
        self.assertEqual(result.status_code, 200, result.text)
        messages = json.loads(calls[0]['input'][0]['text'])['history']['messages']
        self.assertEqual([m['content'] for m in messages], ['First request','First answer','Selected request','MEDIA:'+str(self.file)])
        body_reads = [q for q in queries if 'THEN content' in q]
        self.assertTrue(body_reads)
        for mid in future:
            self.assertFalse(any(f'id={mid}' in q or f'id = {mid}' in q for q in body_reads), body_reads)
        with database(self.home/'state.db') as conn:
            self.assertEqual(list(conn.iterdump()), before)

    def test_pruned_parent_and_mixed_native_indices_keep_proven_history(self):
        self.db.create_session('mixed', source='desktop')
        self.db.append_message('mixed', 'user', 'Original request', timestamp=10)
        self.db.append_message('mixed', 'assistant', 'Original answer', timestamp=11)
        latest = self.db.append_message('mixed', 'user', 'Latest human request', timestamp=12)
        self.db.append_message('mixed', 'assistant', 'Earlier progress', timestamp=13)
        first = self.db.get_messages_as_conversation('mixed')[0]
        self.db.publish_compression_child(parent_session_id='mixed', child_session_id='mixed-tip', source='desktop',
            messages=[first], require_compression_lease=False)
        self.db.append_message('mixed-tip', 'assistant', 'MEDIA:'+str(self.file), timestamp=14)
        self.db.get_messages('mixed', include_compacted=True)
        self.db.get_messages('mixed-tip')
        with database(self.home/'state.db') as conn:
            conn.execute('UPDATE messages SET display_identity=NULL,display_order=NULL WHERE id=?', (latest,))
        selected = self.selected('mixed-tip')
        calls = self.capture_model()
        result = self.client.post('/generation/draft', json={'session_id':'mixed-tip','source':selected['source'], 'previous_exchanges':10})
        self.assertEqual(result.status_code, 200, result.text)
        messages = json.loads(calls[-1]['input'][0]['text'])['history']['messages']
        self.assertEqual([m['content'] for m in messages], ['Original request','Original answer','Latest human request','MEDIA:'+str(self.file)])
        self.assertFalse(result.json()['context']['truncated'])
        with database(self.home/'state.db') as conn:
            conn.execute("UPDATE sessions SET parent_session_id='pruned-parent' WHERE id='fictional'")
        selected = self.selected()
        result = self.client.post('/generation/draft', json={'session_id':'fictional','source':selected['source'], 'previous_exchanges':10})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()['context']['truncated'])
        self.assertEqual(result.json()['context']['previous_exchanges'], 0)

    def test_malformed_or_cyclic_session_provenance_fails_closed(self):
        selected = self.selected()
        calls = self.capture_model()
        cases = [('model_config', value) for value in
                 ('{', '[]', '{"_delegate_from":null}', '{"_reset_from":7}', '{"x":1,"x":2}', '{"x":NaN}')]
        cases += [('parent_session_id','fictional'), ('hidden',1), ('source','cron')]
        for column, value in cases:
            with self.subTest(column=column, value=value):
                with database(self.home/'state.db') as conn:
                    conn.execute("UPDATE sessions SET model_config='{}',parent_session_id=NULL,hidden=0,source='desktop' WHERE id='fictional'")
                    conn.execute(f"UPDATE sessions SET {column}=? WHERE id='fictional'", (value,))
                sessions = self.client.get('/sources/sessions')
                self.assertEqual(sessions.status_code, 200, sessions.text)
                self.assertEqual(sessions.json()['items'], [])
                self.assertNotIn('Meadow survey', sessions.text)
                for response in (
                    self.client.get('/sources/sessions/fictional/artifacts'),
                    self.client.post('/sources/register', json={'title':'No', 'file':selected['file'], 'session_id':'fictional', 'source':selected['source']}),
                    self.client.post('/generation/draft', json={'session_id':'fictional', 'source':selected['source']})):
                    self.assertIn(response.status_code, (404, 422), response.text)
        self.assertEqual(calls, [])
        self.assertEqual(self.client.get('/entries').json()['total'], 0)


if __name__ == '__main__':
    unittest.main()
