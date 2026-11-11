"""Pure output-parser contract tests; no provider, storage or host calls."""
import json
import unittest
from unittest.mock import patch

from preservation.generation import parse_generated


class GeneratedOutputTests(unittest.TestCase):
    def test_generated_values_cannot_be_filename_defaults_or_empty_context(self):
        invalid = [
            ({"title": "STRASSE"}, "text", "Straße.txt"),
            ({"title": "STRASSE.TXT"}, "text", "Straße.txt"),
            *[({"title": title}, "text", "meadow.md") for title in
              ["file", "DOCUMENT", "Report", "untitled", "Delivery"]],
            ({"description": ""}, "text", "meadow.md"),
            ({"description": " \t\n"}, "text", "meadow.md"),
            ({"description": "Saw three birds."}, "history-only", "meadow.pdf"),
            ({"description": "From delivery context only: "}, "history-only", "meadow.pdf"),
            ({"tags": []}, "text", "meadow.md"),
        ]
        for metadata, mode, basename in invalid:
            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(ValueError, "^Invalid generated metadata$"):
                    parse_generated(json.dumps({"status": "ok", "metadata": metadata}),
                                    tuple(sorted(metadata)), mode, basename)
        for mode in ["text", "image", "history-only"]:
            metadata = {"title": "Meadow survey", "description": "From delivery context only: Three swallows.", "tags": ["survey"]}
            result = {"status": "ok", "metadata": metadata}
            self.assertEqual(parse_generated(json.dumps(result), tuple(sorted(metadata)), mode, "meadow.pdf"), result)
        for mode, basename in [(None, "meadow.md"), ("unknown", "meadow.md"), ("text", None)]:
            with self.assertRaisesRegex(ValueError, "^Invalid generation request$"):
                parse_generated('{"status":"insufficient_context"}', ("title",), mode, basename)
        with patch("preservation.metadata.unicodedata.unidata_version", "15.0.0"):
            with self.assertRaisesRegex(RuntimeError, "^Unicode 14 validation unavailable$"):
                parse_generated('{"status":"insufficient_context"}', ("title",), "text", "meadow.md")

    def test_untrusted_json_is_strict_bounded_and_errors_are_fixed(self):
        good = '{"status":"ok","metadata":{"title":"Meadow survey"}}'
        invalid = [None, b'{}', '\ufeff' + good, '```json\n' + good + '\n```',
                   good + good, good + ' prose', '{"status":"ok",}', 'null', '[]',
                   '{"status":"insufficient_context","metadata":{}}',
                   '{"status":"ok","status":"insufficient_context"}',
                   '{"status":"ok","metadata":{"title":"First","title":"Second"}}',
                   '{"status":"ok","metadata":{"title":NaN}}',
                   '{"status":"ok","metadata":{"title":Infinity}}',
                   '{"status":"ok","metadata":{"title":123}}',
                   '{"status":"ok","metadata":{"title":' + '1' * 5000 + '}}',
                   ' ' * 32769 + good, '[' * 2000 + ']' * 2000,
                   '{"status":"ok","metadata":{"title":"\\ud800"}}',
                   '\ud800', '{"status":"ok","metadata":{"title":""}}']
        for raw in invalid:
            with self.subTest(case=invalid.index(raw)):
                with self.assertRaises(ValueError) as error:
                    parse_generated(raw, ("title",), "text", "meadow.md")
                self.assertEqual(str(error.exception), "Invalid generated metadata")
                self.assertIsNone(error.exception.__context__)
        for fields in [(), ("title", "title"), ("unknown",), ("title", "description"), "title"]:
            with self.assertRaisesRegex(ValueError, "^Invalid generation request$"):
                parse_generated(good, fields, "text", "meadow.md")

    def test_exact_requested_fields_and_explicit_insufficient_context(self):
        result = {"status": "ok", "metadata": {"description": "Three swallows recorded."}}
        self.assertEqual(parse_generated(json.dumps(result), ("description",), "text", "meadow.md"), result)
        self.assertEqual(parse_generated(' \n{"status":"insufficient_context"}\t',
                                         ("title",), "text", "meadow.md"),
                         {"status": "insufficient_context"})
        for metadata in [{}, {"title": "Meadow survey"}, {"description": "Birds", "title": "Survey"}]:
            with self.assertRaisesRegex(ValueError, "^Invalid generated metadata$"):
                parse_generated(json.dumps({"status": "ok", "metadata": metadata}),
                                ("description",), "text", "meadow.md")


if __name__ == "__main__":
    unittest.main()
