"""Pure metadata contract tests; no host, storage, or provider calls."""
import unittest
from unittest.mock import patch

from preservation.metadata import validate_metadata


class MetadataTests(unittest.TestCase):
    def test_unicode_boundaries_and_error_precedence(self):
        for payload in [{"title": "😀" * 160}, {"description": "\tA\n"},
                        {"tags": ["İ", "i", "café", "cafe\u0301"]}]:
            self.assertEqual(validate_metadata(payload), payload)
        cases = [
            ({"title": "😀" * 161}, "title/scalar_limit"),
            ({"title": ""}, "title/scalar_limit"),
            ({"title": "\ud800"}, "title/control"),
            ({"title": "\u001c"}, "title/control"),
            ({"title": "\u00a0Title"}, "title/edge_whitespace"),
            ({"title": " "}, "title/edge_whitespace"),
            ({"title": "\u2028"}, "title/control"),
            ({"description": "x" * 4001}, "description/scalar_limit"),
            ({"description": "\r"}, "description/control"),
            ({"description": "\u0085"}, "description/control"),
            ({"tags": ["tag"] * 21}, "tags/scalar_limit"),
            ({"tags": [""]}, "tags[0]/scalar_limit"),
            ({"tags": ["x" * 41]}, "tags[0]/scalar_limit"),
            ({"tags": ["\t"]}, "tags[0]/control"),
            ({"tags": ["tag "]}, "tags[0]/edge_whitespace"),
            ({"tags": ["Straße", "STRASSE"]}, "tags[1]/duplicate"),
            ({"tags": ["Σ", "ς"]}, "tags[1]/duplicate"),
            ({"tags": ["İ", "i\u0307"]}, "tags[1]/duplicate"),
            ({"title": "", "description": None}, "title/scalar_limit"),
        ]
        for payload, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(ValueError) as error:
                    validate_metadata(payload)
                self.assertEqual(str(error.exception), f"Invalid metadata: {reason}")
        with patch("preservation.metadata.unicodedata.unidata_version", "15.0.0"):
            with self.assertRaisesRegex(RuntimeError, "^Unicode 14 validation unavailable$"):
                validate_metadata({"title": "Valid"})

    def test_supplied_empty_values_and_original_unicode_are_preserved(self):
        supplied = {"title": "Café\ufeff", "description": "", "tags": []}
        result = validate_metadata(supplied)
        self.assertEqual(result, supplied)
        self.assertIsNot(result, supplied)
        self.assertIsNot(result["tags"], supplied["tags"])
        self.assertEqual(validate_metadata({}), {})

    def test_invalid_supplied_types_precede_missing_fields(self):
        for payload, message in [
            ({"title": None}, "Invalid metadata: title/type"),
            ({"description": False}, "Invalid metadata: description/type"),
            ({"tags": "tag"}, "Invalid metadata: tags/type"),
            ({"tags": [None]}, "Invalid metadata: tags[0]/type"),
            ({}, "Invalid metadata: title/missing"),
        ]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError) as error:
                    validate_metadata(payload, require_complete=True)
                self.assertEqual(str(error.exception), message)
        for payload in [None, [], {"kind": "document"}]:
            with self.assertRaisesRegex(ValueError, "^Invalid metadata object$"):
                validate_metadata(payload)


if __name__ == "__main__":
    unittest.main()
