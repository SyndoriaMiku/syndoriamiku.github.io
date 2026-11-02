"""Tests for the shared file layer in library_store.py.

Run from the repository root:

    python -m unittest discover -s tests
"""
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import library_store as store


class SaveChaptersTest(unittest.TestCase):
    """library_store.save_chapters: one place for writing chapters + catalog."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.library = os.path.join(self.base, "library")
        os.makedirs(self.library)
        self.catalog_path = os.path.join(self.library, "list.json")

    def tearDown(self):
        self._tmp.cleanup()

    def chapter_path(self, story_slug, chapter_id):
        return os.path.join(self.library, story_slug, chapter_id, "data.json")

    def read_json(self, path):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def read_catalog(self):
        return self.read_json(self.catalog_path)

    def test_new_story_allocates_id_and_writes_each_chapter(self):
        catalog, story_slug, saved = store.save_chapters(
            self.library, self.base, self.catalog_path, None, "Truyện Mới",
            [("0001", "Chương 1", [("漢", "Hán")]), ("0002", "Chương 2", [("", "hai")])])

        self.assertEqual(story_slug, "000001")
        self.assertEqual(saved, ["0001", "0002"])
        self.assertEqual([s["slug"] for s in catalog], ["000001"])
        self.assertEqual([c["id"] for c in catalog[0]["chapters"]], ["0001", "0002"])

        written = self.read_json(self.chapter_path("000001", "0002"))
        self.assertEqual(written["chapter_title"], "Chương 2")
        self.assertEqual(store.unb64(written["content"][0]["vi"]), "hai")

    def test_clash_without_overwrite_aborts_before_any_write(self):
        store.save_chapters(
            self.library, self.base, self.catalog_path, "000001", "Truyện",
            [("0001", "Cũ", [("", "a")])])

        with self.assertRaises(store.ChapterClashError) as caught:
            store.save_chapters(
                self.library, self.base, self.catalog_path, "000001", "Truyện",
                [("0002", "Mới", [("", "b")]), ("0001", "Đụng", [("", "c")])])

        self.assertEqual(caught.exception.chapter_ids, ["0001"])
        self.assertFalse(os.path.exists(self.chapter_path("000001", "0002")))
        self.assertEqual(len(self.read_catalog()[0]["chapters"]), 1)

    def test_overwrite_replaces_content_and_keeps_one_entry(self):
        store.save_chapters(
            self.library, self.base, self.catalog_path, "000001", "Truyện",
            [("0001", "Tên cũ", [("", "a")])])

        catalog, _slug, _saved = store.save_chapters(
            self.library, self.base, self.catalog_path, "000001", "Truyện",
            [("0001", "Tên mới", [("", "b")])], overwrite=True)

        self.assertEqual([c["id"] for c in catalog[0]["chapters"]], ["0001"])
        self.assertEqual(catalog[0]["chapters"][0]["name"], "Tên mới")
        written = self.read_json(self.chapter_path("000001", "0001"))
        self.assertEqual(store.unb64(written["content"][0]["vi"]), "b")

    def test_reads_catalog_fresh_and_keeps_other_stories(self):
        store.save_chapters(
            self.library, self.base, self.catalog_path, None, "Truyện A",
            [("0001", "A1", [("", "x")])])
        catalog, story_slug, _saved = store.save_chapters(
            self.library, self.base, self.catalog_path, None, "Truyện B",
            [("0001", "B1", [("", "y")])])

        self.assertEqual([s["slug"] for s in catalog], ["000001", "000002"])
        self.assertEqual([s["title"] for s in catalog], ["Truyện A", "Truyện B"])
        self.assertEqual(story_slug, "000002")


class CatalogReadTest(unittest.TestCase):
    """read_catalog: missing -> [], broken -> CatalogError (never silently empty)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "list.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_is_an_empty_catalog(self):
        self.assertEqual(store.read_catalog(self.path), [])

    def test_valid_list_is_returned(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write('[{"slug": "000001"}]')
        self.assertEqual(store.read_catalog(self.path), [{"slug": "000001"}])

    def test_broken_json_raises_catalog_error(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("{ not json")
        with self.assertRaises(store.CatalogError):
            store.read_catalog(self.path)

    def test_non_list_json_raises_catalog_error(self):
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write('{"slug": "000001"}')
        with self.assertRaises(store.CatalogError):
            store.read_catalog(self.path)


class ChapterIdTest(unittest.TestCase):
    """Six-digit story ids, four-digit chapter ids, numeric chapter sorting."""

    def test_next_story_id_starts_at_one(self):
        self.assertEqual(store.next_story_id([]), "000001")

    def test_next_story_id_follows_the_highest_numeric_slug(self):
        catalog = [{"slug": "000216"}, {"slug": "notes"}]
        self.assertEqual(store.next_story_id(catalog), "000217")

    def test_next_chapter_id_follows_the_story_highest_id(self):
        catalog = [{"slug": "000001", "chapters": [{"id": "0068"}, {"id": "0010"}]}]
        self.assertEqual(store.next_chapter_id(catalog, "000001"), "0069")

    def test_sort_chapters_is_numeric_and_puts_text_ids_last(self):
        catalog = [{"slug": "000001", "chapters": [{"id": "0010"}, {"id": "oneshot"}, {"id": "0002"}]}]
        store.sort_chapters(catalog)
        self.assertEqual([c["id"] for c in catalog[0]["chapters"]], ["0002", "0010", "oneshot"])


class SplitIntoChaptersTest(unittest.TestCase):
    """Grouping paragraphs by a header regex."""

    def test_groups_by_header_with_a_titleless_lead(self):
        items = ["dẫn", "Chương 1", "A", "Chương 2", "B"]
        groups = store.split_into_chapters(items, r"^chương\s+\d+")
        self.assertEqual([g["title"] for g in groups], ["", "Chương 1", "Chương 2"])
        self.assertEqual([g["items"] for g in groups], [["dẫn"], ["A"], ["B"]])

    def test_text_of_can_read_a_pair(self):
        pairs = [("mở", "dẫn"), ("第一章", "Chương 1"), ("nội", "A")]
        groups = store.split_into_chapters(pairs, r"^chương\s+\d+", text_of=lambda p: p[1])
        self.assertEqual([g["items"] for g in groups], [[("mở", "dẫn")], [("nội", "A")]])

    def test_split_alternatives_ignores_pipes_inside_groups_and_classes(self):
        self.assertEqual(store.split_alternatives(r"^a|(b|c)|[x|y]"), ["^a", "(b|c)", "[x|y]"])

    def test_combine_patterns_deduplicates_alternatives(self):
        combined = store.combine_patterns(r"^a|^b", r"^b|^c")
        self.assertEqual(combined, "^a|^b|^c")


class ReplaceInStoryTest(unittest.TestCase):
    """replace_in_story: count first, then apply with a backup copy."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.library = os.path.join(self.base, "library")
        os.makedirs(self.library)
        self.catalog_path = os.path.join(self.library, "list.json")
        store.save_chapters(
            self.library, self.base, self.catalog_path, None, "Truyện",
            [("0001", "Chương 1", [("", "Xin chào thế giới")])])
        self.catalog = store.read_catalog(self.catalog_path)

    def tearDown(self):
        self._tmp.cleanup()

    def chapter_data(self):
        path = os.path.join(self.library, "000001", "0001", "data.json")
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def test_preview_counts_without_writing(self):
        preview = store.replace_in_story(self.library, self.catalog, "000001", re.compile("thế giới"), "trần gian")
        self.assertEqual(preview["total"], 1)
        self.assertEqual(preview["chapters"], [("0001", 1)])
        self.assertIsNone(preview["backup"])
        self.assertEqual(store.unb64(self.chapter_data()["content"][0]["vi"]), "Xin chào thế giới")

    def test_apply_writes_text_and_backs_up_the_old_file(self):
        backup_root = os.path.join(self.base, "backups")
        result = store.replace_in_story(
            self.library, self.catalog, "000001", re.compile("thế giới"), "trần gian",
            apply=True, backup_root=backup_root)
        self.assertEqual(store.unb64(self.chapter_data()["content"][0]["vi"]), "Xin chào trần gian")
        self.assertTrue(os.path.isfile(os.path.join(result["backup"], "0001", "data.json")))

    def test_apply_updates_the_catalog_chapter_name(self):
        store.replace_in_story(
            self.library, self.catalog, "000001", re.compile("chương 1", re.IGNORECASE), "Hồi 1",
            apply=True)
        self.assertEqual(self.catalog[0]["chapters"][0]["name"], "Hồi 1")
        with open(os.path.join(self.library, "000001", "0001", "data.json"), "r", encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["chapter_title"], "Hồi 1")


class DecodeTextBytesTest(unittest.TestCase):
    """Chinese text files arrive as UTF-8, UTF-16 BOM, GB18030 or Big5."""

    def test_utf8_bom(self):
        text, encoding = store.decode_text_bytes("\ufeff中文".encode("utf-8"))
        self.assertEqual((text, encoding), ("中文", "UTF-8 BOM"))

    def test_utf16(self):
        text, encoding = store.decode_text_bytes("中文".encode("utf-16"))
        self.assertEqual((text, encoding), ("中文", "UTF-16"))

    def test_plain_utf8(self):
        text, encoding = store.decode_text_bytes("中文".encode("utf-8"))
        self.assertEqual((text, encoding), ("中文", "UTF-8"))

    def test_gb18030(self):
        text, encoding = store.decode_text_bytes("中文".encode("gb18030"))
        self.assertEqual((text, encoding), ("中文", "GB18030"))


if __name__ == "__main__":
    unittest.main()
