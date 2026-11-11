#!/usr/bin/env python3
"""Run the complete pure metadata contract on its real Unicode-14 runtime."""
import sys
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Direct script execution otherwise places only scripts/ on the import path.
sys.path.insert(0, str(ROOT))
EXPECTED_TESTS = {
    "test_generation_contract.GeneratedOutputTests.test_generated_values_cannot_be_filename_defaults_or_empty_context",
    "test_generation_contract.GeneratedOutputTests.test_untrusted_json_is_strict_bounded_and_errors_are_fixed",
    "test_generation_contract.GeneratedOutputTests.test_exact_requested_fields_and_explicit_insufficient_context",
    "test_preservation_metadata.MetadataTests.test_unicode_boundaries_and_error_precedence",
    "test_preservation_metadata.MetadataTests.test_supplied_empty_values_and_original_unicode_are_preserved",
    "test_preservation_metadata.MetadataTests.test_invalid_supplied_types_precede_missing_fields",
}


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def main():
    print(f"Python {sys.version}; Unicode {unicodedata.unidata_version}", flush=True)
    if sys.version_info[:2] != (3, 11) or unicodedata.unidata_version != "14.0.0":
        raise SystemExit("Metadata contracts require real Python 3.11 / Unicode 14.0.0")
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests" / "preservation"), pattern="test_*.py")
    discovered = list(test_ids(suite))
    if loader.errors or len(discovered) != len(EXPECTED_TESTS) or set(discovered) != EXPECTED_TESTS:
        raise SystemExit(f"Metadata test manifest mismatch: {discovered!r}; {loader.errors!r}")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if (not result.wasSuccessful() or result.skipped or result.expectedFailures
            or result.testsRun != len(EXPECTED_TESTS)):
        raise SystemExit("Metadata contracts failed, were skipped, had expected failures, or did not all execute")


if __name__ == "__main__":
    main()
