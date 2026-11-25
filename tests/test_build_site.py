import base64
import gzip
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import build_site  # noqa: E402


def b64(text):
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


class BuildSiteTest(unittest.TestCase):
    def test_compact_data_roundtrip(self):
        src = {'title': 'Truyện', 'content': [{'cn': b64('你好'), 'vi': b64('Xin chào ~ bạn')}, {'cn': '', 'vi': b64('Hết')}]}
        out = json.loads(gzip.decompress(build_site.compact_data(json.dumps(src).encode())))
        self.assertEqual(out['title'], 'Truyện')
        self.assertEqual(out['content'][0], {'cn': '~你好', 'vi': '~Xin chào ~ bạn'})
        self.assertEqual(out['content'][1], {'cn': '', 'vi': '~Hết'})

    def test_plain_keeps_invalid_base64(self):
        self.assertEqual(build_site.plain('không phải base64'), 'không phải base64')
        self.assertEqual(build_site.plain(''), '')

    def test_patch_story_reader(self):
        html = ("<html><head><meta charset='utf-8'></head><body><script>"
                "$.getJSON('./data.json', function (data) { go(data); }).fail(x);</script></body></html>")
        out = build_site.patch_reader_html(html.encode()).decode()
        self.assertTrue(out.startswith('<html><head>' + build_site.LOADER_TAG))
        self.assertIn("ChapterData.jq('./data.json', function (data) {", out)
        self.assertEqual(build_site.patch_reader_html(out.encode()).decode().count(build_site.LOADER_SRC), 1)

    def test_set_data_base(self):
        with open(os.path.join(build_site.ROOT, 'library', 'assets', 'chapter-data.js'), 'rb') as f:
            src = f.read()
        out = build_site.set_data_base(src, 'https://stv-data.example.workers.dev').decode()
        self.assertIn('window.CHAPTER_DATA_BASE || "https://stv-data.example.workers.dev"', out)
        self.assertNotIn(build_site.DATA_BASE_MARKER, out)

    def test_data_base_requires_data_dir(self):
        with self.assertRaises(SystemExit):
            build_site.main('_unused', None, 'https://x.workers.dev')
        with self.assertRaises(SystemExit):
            build_site.main('_unused', '_unused_data', 'http://insecure.example')

    def test_excluded(self):
        for path in ('builder.py', 'dist/StoryStudio.exe', 'tests/test_x.py', 'name.cfg', 'README.md',
                     'tools/build_site.py', '.github/workflows/pages.yml', 'cloudflare/worker.js'):
            self.assertTrue(build_site.excluded(path), path)
        for path in ('index.html', 'library/list.json', 'library/000001/0001/data.json',
                     'stories/a/index.html', 'library/assets/chapter-data.js', 'elo-web/readme.md'):
            self.assertFalse(build_site.excluded(path), path)


if __name__ == '__main__':
    unittest.main()
