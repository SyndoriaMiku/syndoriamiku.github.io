"""Tests for git_sync.py: auto commit + push after a library save.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import git_sync
import library_store as store


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True)


class AutocommitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.repo = os.path.join(self.base, "repo")
        self.remote = os.path.join(self.base, "remote.git")
        os.makedirs(os.path.join(self.repo, "library", "000001", "0001"))
        os.makedirs(os.path.join(self.repo, "stories"))
        git(self.base, "init", "--bare", "-b", "main", self.remote)
        git(self.base, "init", "-b", "main", self.repo)
        git(self.repo, "remote", "add", "origin", self.remote)
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "t@example.com")
        with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
            stream.write("[]")
        with open(os.path.join(self.repo, "stories", "note.txt"), "w", encoding="utf-8") as stream:
            stream.write("x")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "init")
        git(self.repo, "push", "origin", "HEAD")

    def tearDown(self):
        self._tmp.cleanup()

    def commit_subject(self):
        return git(self.repo, "log", "-1", "--pretty=%s").stdout.strip()

    def test_commits_and_pushes_library_content(self):
        with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
            stream.write('[{"slug": "000001"}]')

        sha = git_sync.commit_and_push(self.repo, message="`feat` add new stories")

        self.assertTrue(sha)
        self.assertEqual(self.commit_subject(), "`feat` add new stories")
        pushed = git(self.remote, "log", "-1", "--pretty=%s", "main").stdout.strip()
        self.assertEqual(pushed, "`feat` add new stories")

    def test_other_changes_are_left_out_of_the_commit(self):
        with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
            stream.write('[{"slug": "000001"}]')
        with open(os.path.join(self.repo, "stories", "note.txt"), "w", encoding="utf-8") as stream:
            stream.write("y")
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as stream:
            stream.write("not a story")

        git_sync.commit_and_push(self.repo)

        committed = git(self.repo, "show", "--name-only", "--pretty=", "HEAD").stdout.split()
        self.assertEqual(sorted(committed), ["library/list.json", "stories/note.txt"])
        self.assertTrue(git(self.repo, "status", "--porcelain", "README.md").stdout.strip())

    def test_nothing_to_commit_returns_none(self):
        self.assertIsNone(git_sync.commit_and_push(self.repo))

    def _push_from_other_clone(self, name="web.txt"):
        """Giả lập trình sửa trên web: một commit khác lên origin trước."""
        other = os.path.join(self.base, "other")
        git(self.base, "clone", "-q", self.remote, other)
        git(other, "config", "user.name", "Web")
        git(other, "config", "user.email", "w@example.com")
        with open(os.path.join(other, "stories", name), "w", encoding="utf-8") as stream:
            stream.write("from web")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "web edit")
        git(other, "push", "-q", "origin", "HEAD")

    def test_rejected_push_rebases_and_retries(self):
        self._push_from_other_clone()
        with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
            stream.write('[{"slug": "000002"}]')
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as stream:
            stream.write("dirty, not a story")   # thay đổi khác của người dùng: autostash giữ nguyên

        self.assertTrue(git_sync.commit_and_push(self.repo))

        log = git(self.remote, "log", "--pretty=%s", "main").stdout.split("\n")
        self.assertEqual(log[:2], ["`feat` add new stories", "web edit"])
        with open(os.path.join(self.repo, "README.md"), encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "dirty, not a story")

    def test_stuck_commit_is_pushed_on_next_save(self):
        with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
            stream.write('[{"slug": "000003"}]')
        git(self.repo, "commit", "-q", "-am", "saved while offline")   # commit đã có, push chưa
        self.assertTrue(git_sync.commit_and_push(self.repo))
        pushed = git(self.remote, "log", "-1", "--pretty=%s", "main").stdout.strip()
        self.assertEqual(pushed, "saved while offline")

    def test_waits_for_index_lock(self):
        import threading
        lock = os.path.join(self.repo, ".git", "index.lock")
        open(lock, "w").close()
        threading.Timer(1.0, os.remove, args=(lock,)).start()
        with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
            stream.write('[{"slug": "000004"}]')
        self.assertTrue(git_sync.commit_and_push(self.repo))

    def test_async_failure_reaches_listener(self):
        messages = []
        listener = lambda message, ok: messages.append((ok, message))
        git_sync.add_listener(listener)
        try:
            git(self.repo, "remote", "set-url", "origin", os.path.join(self.base, "missing.git"))
            with open(os.path.join(self.repo, "library", "list.json"), "w", encoding="utf-8") as stream:
                stream.write('[{"slug": "000005"}]')
            git_sync.autocommit_async(self.repo).join(60)
        finally:
            git_sync.remove_listener(listener)
        self.assertEqual(len(messages), 1)
        self.assertFalse(messages[0][0])
        self.assertIn("chưa đẩy được", messages[0][1])

    def test_non_repo_directory_returns_none(self):
        outside = os.path.join(self.base, "plain")
        os.makedirs(outside)
        self.assertIsNone(git_sync.commit_and_push(outside))


class WriteCatalogHookTest(unittest.TestCase):
    """Every library save goes through write_catalog, which must trigger the sync."""

    def test_write_catalog_requests_a_commit_of_the_project_root(self):
        with tempfile.TemporaryDirectory() as base:
            library = os.path.join(base, "library")
            os.makedirs(library)
            calls = []
            original = git_sync.autocommit_async
            git_sync.autocommit_async = lambda path, message=git_sync.COMMIT_MESSAGE: calls.append(path)
            try:
                store.write_catalog(os.path.join(library, "list.json"), [])
            finally:
                git_sync.autocommit_async = original
            self.assertEqual(calls, [base])


if __name__ == "__main__":
    unittest.main()
