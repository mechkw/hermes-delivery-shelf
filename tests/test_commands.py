"""Slash-command contracts through Hermes dispatch and public tool readback."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(os.environ.get("HERMES_SOURCE", Path.home() / ".hermes/hermes-agent"))))
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from hermes_cli.plugin_command_dispatch import invoke_plugin_command

spec = importlib.util.spec_from_file_location("shelf_command_plugin", ROOT / "__init__.py")
assert spec is not None and spec.loader is not None
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class Context:
    def __init__(self):
        self.commands = {}
        self.tools = {}
        self.injected = []
        self.accept = True

    def inject_message(self, content, role="user", **kwargs):
        self.injected.append((content, role, kwargs))
        return self.accept

    def register_command(self, name, handler, **kwargs):
        self.commands[name] = handler

    def register_tool(self, *, name, handler, **kwargs):
        self.tools[name] = handler


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="shelf-command-", dir=os.environ.get("TMPDIR"))
        self.home = Path(self.tmp.name) / "home"
        (self.home / "workspaces").mkdir(parents=True)
        (self.home / "workspaces" / "approved image.png").write_bytes(b"fictional file")
        self.token = set_hermes_home_override(self.home)
        self.ctx = Context()
        plugin.register(self.ctx)

    def tearDown(self):
        reset_hermes_home_override(self.token)
        self.tmp.cleanup()

    def command(self, text, **context):
        return invoke_plugin_command(self.ctx.commands["shelf"], text, platform="telegram", **context)

    def entries(self, **args):
        result = json.loads(self.ctx.tools["delivery_shelf_search"](args))
        self.assertTrue(result["ok"], result)
        return result["data"]

    def test_mixed_case_supplied_metadata_direct_save(self):
        reply = self.command('add OpsCase #Keep-Tag, keep-tag, Équipe, équipe --description "Exact description." --file "workspaces:approved image.png"')
        self.assertIn('Saved', reply)
        self.assertIn('Keep-Tag', reply)
        item = self.entries(tag='KEEP-TAG')['items'][0]
        self.assertEqual(item['title'], 'OpsCase')
        self.assertEqual(item['tags'], ['Keep-Tag', 'Équipe'])
        self.assertEqual(item['description'], 'Exact description.')
        self.assertEqual(self.ctx.injected, [])

    def test_mixed_case_handoff_then_fixture_completion_preserves_supplied_fields(self):
        reply = self.command('add OpsCase #Keep-Tag, keep-tag --file "workspaces:approved image.png"',
                             session_id='fictional-session', session_key='telegram:fictional')
        self.assertIsNone(reply)
        self.assertEqual(self.entries()['total'], 0)
        payload = json.loads(self.ctx.injected[-1][0].split('\n', 1)[1])
        self.assertEqual(payload['missing'], ['description'])
        self.assertEqual(payload['supplied']['title'], 'OpsCase')
        self.assertEqual(payload['supplied']['tags'], ['Keep-Tag'])
        # Fixture completion exercises the save seam, not real-model adherence.
        saved = json.loads(self.ctx.tools['delivery_shelf_register']({
            **payload['supplied'], 'description': 'Fictional completed description.'}))
        self.assertTrue(saved['ok'], saved)
        result = self.entries(tag='keep-tag')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['id'], saved['data']['id'])
        self.assertEqual(result['items'][0]['title'], 'OpsCase')
        self.assertEqual(result['items'][0]['tags'], ['Keep-Tag'])

    def test_add_explicit_file_title_tags_and_native_context(self):
        reply = self.command('add Approved plugin artwork #branding, plugins --description "Approved release image." --file "workspaces:approved image.png"', session_id="fictional-session")
        self.assertIn("Saved", reply)
        result = self.entries(q="Approved plugin artwork")
        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["title"], "Approved plugin artwork")
        self.assertEqual(item["tags"], ["branding", "plugins"])
        self.assertEqual(item["description"], "Approved release image.")
        self.assertIn("Approved release image.", reply)
        self.assertEqual(self.ctx.injected, [])
        self.assertEqual(item["file"], {"root": "workspaces", "path": "approved image.png"})
        self.assertEqual(item["session_id"], "fictional-session")
        self.assertIn(item["id"], reply)
        self.assertIn("Approved plugin artwork", self.command("artwork"))


    def test_plain_title_no_context_and_explicit_search(self):
        title = "Artist's C# résumé"
        reply = self.command('add ' + title + ' #code --description "Language guide." --file "workspaces:approved image.png"')
        self.assertIn("Saved", reply)
        item = self.entries()["items"][0]
        self.assertEqual(item["title"], title)
        self.assertEqual(item["tags"], ["code"])
        self.assertEqual(item["session_id"], "")
        self.assertIn(title, self.command("search C#"))
        self.assertIn(title, self.command(""))
        self.assertEqual(self.entries()["total"], 1)

    def test_profile_isolation_and_link_denial(self):
        self.assertIn("Saved", self.command('add Alpha #alpha --description "Alpha image." --file "workspaces:approved image.png"'))
        other = Path(self.tmp.name) / "profiles" / "other"
        (other / "workspaces").mkdir(parents=True)
        token = set_hermes_home_override(other)
        try:
            self.assertEqual(self.entries()["total"], 0)
            self.assertNotIn("Saved", self.command('add Wrong profile #other --description "Missing." --file "workspaces:approved image.png"'))
            (other / "workspaces" / "linked.png").symlink_to(self.home / "workspaces" / "approved image.png")
            self.assertNotIn("Saved", self.command('add Link #link --description "Unsafe." --file workspaces:linked.png'))
            self.assertEqual(self.entries()["total"], 0)
        finally:
            reset_hermes_home_override(token)
        self.assertEqual(self.entries()["total"], 1)

    def test_whitespace_and_tag_normalization(self):
        reply = self.command('add\tRésumé C# guide #Branding, plugins, BRANDING --description "Guide."\t--file\t"workspaces:approved image.png"')
        self.assertIn("Saved", reply)
        self.assertEqual(self.entries()["items"][0]["tags"], ["Branding", "plugins"])

    def test_missing_metadata_hands_off_without_premature_save(self):
        reply = self.command('add --file "workspaces:approved image.png"', session_id="fictional-session", session_key="telegram:fictional")
        self.assertIsNone(reply)
        self.assertEqual(self.entries()["total"], 0)
        self.assertEqual(len(self.ctx.injected), 1)
        prompt, role, target = self.ctx.injected[0]
        self.assertEqual(role, "user")
        self.assertEqual(target, {"session_key": "telegram:fictional"})
        self.assertIn('"missing": ["title", "tags", "description"]', prompt)
        self.assertIn('"path": "approved image.png"', prompt)
        self.assertIn("delivery_shelf_register", prompt)
        self.assertIn("delivery_shelf_search", prompt)
        self.assertIn("Only after", prompt)

    def test_partial_metadata_and_denied_handoff(self):
        text = 'add My exact title #branding --file "workspaces:approved image.png"'
        self.ctx.accept = False
        reply = self.command(text, session_id="fictional-session", session_key="telegram:fictional")
        self.assertIn("not saved", reply)
        self.assertIn("allow_gateway_injection", reply)
        self.assertEqual(self.entries()["total"], 0)
        prompt = self.ctx.injected[0][0]
        self.assertIn('"title": "My exact title"', prompt)
        self.assertIn('"tags": ["branding"]', prompt)
        self.assertIn('"missing": ["description"]', prompt)
        self.ctx.injected.clear()
        reply = self.command(text)
        self.assertIn("not saved", reply)
        self.assertEqual(self.ctx.injected, [])

    def test_description_only_preserved_and_invalid_options_rejected(self):
        reply = self.command('add --description "Keep #hash and --file words." --file "workspaces:approved image.png"',
                             session_id="fictional-session", session_key="telegram:fictional")
        self.assertIsNone(reply)
        self.assertIn('"description": "Keep #hash and --file words."', self.ctx.injected[0][0])
        for text in ('add --file "workspaces:approved image.png" --description',
                     'add --file "workspaces:approved image.png" --description a --description b',
                     'add --file "workspaces:approved image.png" --unknown value'):
            self.ctx.injected.clear()
            self.assertIn("not saved", self.command(text, session_id="fictional-session", session_key="telegram:fictional"))
            self.assertEqual(self.ctx.injected, [])
        self.assertEqual(self.entries()["total"], 0)

    def test_agent_can_correct_saved_metadata_without_duplicate(self):
        self.command('add Original #branding --description "First description." --file "workspaces:approved image.png"')
        item = self.entries()["items"][0]
        self.assertIn("delivery_shelf_update", self.ctx.tools)
        fields = {key: value for key, value in item.items() if key not in ("created", "updated")}
        fields.update(title="Corrected title", tags=["release"], description="Corrected description.")
        response = json.loads(self.ctx.tools["delivery_shelf_update"](fields))
        self.assertTrue(response["ok"], response)
        result = self.entries(q="Corrected title")
        self.assertEqual(result["total"], 1)
        corrected = result["items"][0]
        self.assertEqual(corrected["id"], item["id"])
        self.assertEqual(corrected["revision"], 2)
        self.assertEqual(corrected["file"], item["file"])
        self.assertEqual(corrected["tags"], ["release"])
        self.assertEqual(corrected["description"], "Corrected description.")
        self.assertFalse(json.loads(self.ctx.tools["delivery_shelf_update"](fields))["ok"])
        for revision in (True, 1.0, 9007199254740992):
            fields["revision"] = revision
            self.assertFalse(json.loads(self.ctx.tools["delivery_shelf_update"](fields))["ok"])
        self.assertEqual(self.entries()["total"], 1)
        self.assertEqual(self.entries()["items"][0], corrected)

    def test_recent_artifacts_add_handoff_is_bound_and_does_not_save_early(self):
        reply = self.command('add', session_id='fictional-session', session_key='telegram:fictional')
        self.assertIsNone(reply)
        self.assertEqual(self.entries()['total'], 0)
        prompt, role, target = self.ctx.injected[-1]
        self.assertEqual(role, 'user')
        self.assertEqual(target, {'session_key': 'telegram:fictional'})
        for text in ('most recent', 'related set', 'delivery_shelf_search',
                     'delivery_shelf_register', 'no filesystem scans', 'readback'):
            self.assertIn(text, prompt)
        data = json.loads(prompt.split('\n', 1)[1])
        self.assertEqual(data['session_id'], 'fictional-session')
        self.assertEqual(data['intent'], 'save_recent_artifacts')

    def test_recent_add_denied_missing_context_and_invalid_session(self):
        for args in ({}, {'session_id': 'fictional-session'},
                     {'session_id': '../bad', 'session_key': 'telegram:fictional'}):
            self.assertIn('not saved', self.command('add', **args))
        self.assertEqual(self.ctx.injected, [])
        self.ctx.accept = False
        self.assertIn('not saved', self.command('add', session_id='fictional-session', session_key='telegram:fictional'))
        self.assertEqual(self.entries()['total'], 0)

    def test_invalid_add_is_not_saved(self):
        cases = [
            'add', 'add Title', 'add Title #',
            'add Title #branding, --file "workspaces:approved image.png"',
            'add Title #,plugins --file "workspaces:approved image.png"',
            'add Title --file workspaces:missing.png',
            'add Title --file workspaces:../outside.png',
            'add Title --file workspaces:/absolute.png',
            'add Title --file workspaces:.hidden.png',
            'add Title --file unknown:report.png',
            'add Title --file "workspaces:approved image.png" extra',
            'add Title --file "unterminated',
            'add Title --file x:y --file "workspaces:approved image.png"',
            'add ' + 'x' * 161 + ' --file "workspaces:approved image.png"',
            'add Title #' + 'x' * 41 + ' --file "workspaces:approved image.png"',
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertNotIn("Saved to", self.command(text))
                self.assertEqual(self.entries()["total"], 0)


if __name__ == "__main__":
    unittest.main()
