"""ReviewWindow.load_content inserts a long document in batches.

A synchronous insert blocks the Tk main loop, so the window appears frozen
until every paragraph is in. The contract: load_content returns before the
whole document is inserted, and the remaining lines arrive on idle time.

Needs tkinter (skipped when unavailable). builder.py also imports
tkinterdnd2, which is not needed for ReviewWindow; a minimal stub stands in
when the package is absent so the test can still run.

Run from the repository root:

    python -m unittest discover -s tests
"""
import os
import sys
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.withdraw()
    _root.destroy()
    TK_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the host
    TK_AVAILABLE = False


def _load_builder():
    try:
        import tkinterdnd2  # noqa: F401
    except ImportError:
        stub = types.ModuleType("tkinterdnd2")
        stub.DND_FILES = "DND_Files"
        stub.TkinterDnD = types.SimpleNamespace(Tk=tk.Tk)
        sys.modules["tkinterdnd2"] = stub
    import builder
    return builder


@unittest.skipUnless(TK_AVAILABLE, "tkinter unavailable")
class LoadContentBatchingTest(unittest.TestCase):

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_long_document_is_inserted_in_batches_then_completes(self):
        builder = _load_builder()
        pairs = 20000
        cn_lines = ["第一章"] * pairs
        vi_lines = ["Chương một"] * pairs
        expected = "".join(f"{cn}\n{vi}\n\n" for cn, vi in zip(cn_lines, vi_lines))

        window = builder.ReviewWindow(
            self.root, "Batching", "batching-test", cn_lines, vi_lines,
            app_instance=None, from_draft=True)

        text = window.text_editor
        # load_content must have returned with the document still incomplete.
        self.assertLess(len(text.get("1.0", "end-1c")), len(expected))

        deadline = time.time() + 30
        while len(text.get("1.0", "end-1c")) < len(expected) and time.time() < deadline:
            self.root.update()
            time.sleep(0.005)

        self.assertEqual(text.get("1.0", "end-1c"), expected)


if __name__ == "__main__":
    unittest.main()
