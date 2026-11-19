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
