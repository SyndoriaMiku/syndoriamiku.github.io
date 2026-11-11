"""A fine-tuned NER folder must be accepted once its manifest is a custom one.

Run from the repository root:

    python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gpu_name_scanner as scanner


class IsInstalledTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = self._tmp.name
        for name in ("config.json", scanner.WEIGHTS, "vocab.txt"):
            with open(os.path.join(self.path, name), "w", encoding="utf-8") as stream:
                stream.write("{}")

    def tearDown(self):
        self._tmp.cleanup()

    def manifest(self, data):
        with open(os.path.join(self.path, scanner.MANIFEST), "w", encoding="utf-8") as stream:
            json.dump(data, stream)

    def test_base_manifest_with_the_pinned_revision_is_installed(self):
        self.manifest({"model": scanner.MODEL, "revision": scanner.REVISION})
        self.assertTrue(scanner.is_installed(self.path))

    def test_base_manifest_with_a_different_revision_is_not_installed(self):
        self.manifest({"model": scanner.MODEL, "revision": "0" * 40})
        self.assertFalse(scanner.is_installed(self.path))

    def test_custom_manifest_with_matching_labels_is_installed(self):
        self.manifest({"custom": True, "labels": scanner.LABELS})
        self.assertTrue(scanner.is_installed(self.path))

    def test_custom_manifest_with_wrong_labels_is_not_installed(self):
        self.manifest({"custom": True, "labels": list(reversed(scanner.LABELS))})
        self.assertFalse(scanner.is_installed(self.path))

    def test_missing_tokenizer_files_is_not_installed(self):
        os.remove(os.path.join(self.path, "vocab.txt"))
        self.manifest({"custom": True, "labels": scanner.LABELS})
        self.assertFalse(scanner.is_installed(self.path))

    def test_custom_manifest_helper(self):
        self.manifest({"custom": True, "labels": scanner.LABELS})
        self.assertTrue(scanner.custom_manifest(self.path))
        self.manifest({"model": scanner.MODEL, "revision": scanner.REVISION})
        self.assertFalse(scanner.custom_manifest(self.path))


if __name__ == "__main__":
    unittest.main()
