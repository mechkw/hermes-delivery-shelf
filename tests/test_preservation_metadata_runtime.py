"""Exercise refusal on the actual newer host runtime, without patching tables."""
import unicodedata
import unittest

from preservation.metadata import validate_metadata


class MetadataRuntimeTests(unittest.TestCase):
    @unittest.skipIf(unicodedata.unidata_version == "14.0.0", "Unicode-14 success contracts run separately")
    def test_actual_unsupported_runtime_refuses_before_metadata_validation(self):
        # A valid patch, empty patch and invalid input must all fail closed.
        # The pinned Python 3.14 host job executes this test, never this skip.
        self.assertNotEqual(unicodedata.unidata_version, "14.0.0")
        for payload in ({"title": "Valid", "description": "", "tags": []}, {}, {"title": None}):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(RuntimeError, "^Unicode 14 validation unavailable$"):
                    validate_metadata(payload)


if __name__ == "__main__":
    unittest.main()
