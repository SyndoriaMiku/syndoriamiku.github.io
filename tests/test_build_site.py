import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import build_site  # noqa: E402


class BuildSiteTest(unittest.TestCase):
    def test_excluded(self):
        for path in ('builder.py', 'dist/StoryStudio.exe', 'tests/test_x.py', 'name.cfg', 'README.md',
                     'tools/build_site.py', '.github/workflows/pages.yml', 'cloudflare/worker.js', 'r2_store.py'):
            self.assertTrue(build_site.excluded(path), path)
        for path in ('index.html', '404.html', 'reader.html', 'library/index.html', 'library/chapter.html',
                     'library/assets/chapter-data.js', 'stories/index.html', 'elo-web/readme.md'):
            self.assertFalse(build_site.excluded(path), path)


if __name__ == '__main__':
    unittest.main()
