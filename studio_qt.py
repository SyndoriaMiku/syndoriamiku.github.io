"""Story Studio (bản Qt): dịch truyện (builder_qt) và biên tập thư viện (editor_qt) trong một cửa sổ.

Chạy: python studio_qt.py   (hoặc pythonw studio_qt.py để không hiện cửa sổ console)
builder_qt.py và editor_qt.py vẫn chạy riêng được.
"""
import os
import sys

# pythonw không có console: sys.stdout/stderr là None, thư viện nào in ra (thanh tải
# model, print lỗi) sẽ hỏng. Ghi tất cả vào studio.log cạnh file này để còn xem lỗi.
if sys.stdout is None or sys.stderr is None:
    _here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    _log = open(os.path.join(_here, "studio.log"), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget

import builder_qt
import editor_core
import editor_qt
import translator_core as core
from qt_widgets import STYLE, restore_geometry, save_geometry

TABS = (("translate", "🈶  Dịch truyện"), ("library", "📚  Biên tập thư viện"))


class StoryStudio(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Story Studio")
        restore_geometry(self, "studio_main", 1300, 780)
        self.setMinimumSize(1040, 680)
        self.setDocumentMode(True)
        self.setStyleSheet(
            "QTabBar { background: #100e0b; }"
            "QTabBar::tab { background: #100e0b; color: #8a7f70; padding: 9px 22px; font-weight: bold;"
            "  border: none; border-bottom: 3px solid #100e0b; }"
            "QTabBar::tab:selected { background: #15130f; color: #f4ede1; border-bottom-color: #d9a35c; }"
            "QTabBar::tab:hover:!selected { color: #d6cebf; }")
        self.translator = builder_qt.TranslatorWindow(embedded=True)
        self.editor = editor_qt.EditorWindow(embedded=True)
        self.addTab(self.translator, TABS[0][1])
        self.addTab(self.editor, TABS[1][1])
        hint = QLabel("Ctrl+1 / Ctrl+2 để chuyển tab  ")
        hint.setStyleSheet("color: #6b6255; font-size: 9pt; background: transparent;")
        self.setCornerWidget(hint, Qt.TopRightCorner)
        for i in range(len(TABS)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, lambda i=i: self.setCurrentIndex(i))
        self._catalog_stamp = self._catalog_mtime()
        start = core.load_config().get("studio_tab", "translate")
        self.setCurrentIndex(next((i for i, (key, _l) in enumerate(TABS) if key == start), 0))
        self._on_tab(self.currentIndex())
        self.currentChanged.connect(self._on_tab)

    def _catalog_mtime(self):
        try:
            return os.path.getmtime(editor_core.CATALOG_PATH)
        except OSError:
            return None

    def _on_tab(self, index):
        key, text = TABS[index]
        self.setWindowTitle(f"Story Studio — {text.split(maxsplit=1)[-1]}")
        core.save_config({"studio_tab": key})
        if key == "library":
            # Trang Dịch có thể vừa lưu truyện/chương vào thư viện: nạp lại danh mục.
            stamp = self._catalog_mtime()
            if stamp != self._catalog_stamp:
                self._catalog_stamp = stamp
                self.editor.load_story_list()
                if self.editor.story_combo.is_valid():
                    self.editor.on_story_selected()

    def closeEvent(self, event):
        # Hỏi chương chưa lưu trước: huỷ ở đây thì chưa động gì tới bản đang dịch.
        if self.editor.is_dirty():
            self.setCurrentIndex(1)
        if not self.editor.can_close():
            event.ignore()
            return
        if not self.translator.can_close():
            self.setCurrentIndex(0)
            event.ignore()
            return
        save_geometry(self, "studio_main")
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Story Studio")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = StoryStudio()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
