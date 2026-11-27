"""Trình biên tập thư viện (bản Qt / PySide6): sửa/lưu chương, mở nguồn JSON, phân chương tự động,
tìm & thay (cả truyện). Thay editor.py (Tk) — gõ IME ngay trong ô như builder_qt.py.
Phần xử lý dùng chung: editor_core.py.

Chạy: python editor_qt.py
"""
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut, QTextCursor, QTextFormat
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QCompleter, QDialog, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

import library_store as store
import editor_core as ec
from library_store import CatalogError, read_catalog, write_catalog
from qt_widgets import (ACCENT, ERROR, HINT, STYLE, FindBar, LineEdit, PlainTextEdit, ask_yes_no,
                        ask_yes_no_cancel, button, error, info, label, py_offset, qt_offsets, raw_text,
                        restore_geometry, save_geometry, selected_text, set_label, warn)
from translator_core import BG, FIELD, MUTED, PANEL, TEXT

CARD = "#1e1b17"
GOLD = "#d9a35c"
FLASH_COLORS = {"ok": GOLD, "warn": "#e8c27a", "error": ERROR, "info": MUTED}


def hbox(*items, margins=(0, 0, 0, 0), spacing=6):
    row = QHBoxLayout()
    row.setContentsMargins(*margins)
    row.setSpacing(spacing)
    for item in items:
        if item == "stretch":
            row.addStretch(1)
        elif isinstance(item, tuple):
            row.addWidget(item[0], item[1])
        else:
            row.addWidget(item)
    return row


def head(text):
    return label(text, MUTED, 9, True)


class StoryPicker(LineEdit):
    """Ô chọn truyện: gõ tên/mã (không dấu, đủ mọi từ) để lọc, ↓/F4 mở toàn bộ danh sách.
    Phát ``picked(text)`` khi chọn một mục."""
    picked = Signal(str)

    def __init__(self, options=()):
        super().__init__()
        self.options = list(options)
        self.setPlaceholderText("Gõ tên hoặc mã truyện…")
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._completer.setMaxVisibleItems(14)
        self._completer.setWidget(self)
        self._completer.activated.connect(self._choose)
        self._completer.popup().setStyleSheet(f"background: {FIELD}; color: white; selection-background-color: {ACCENT};")
        self.textEdited.connect(self._filter)
        self.returnPressed.connect(self._enter)

    def set_options(self, options):
        self.options = list(options)

    def value(self):
        return self.text().strip()

    def is_valid(self):
        return self.value() in self.options

    def _filter(self, text):
        self._model.setStringList(ec.filter_options(self.options, text)[:300])
        if self._model.rowCount():
            self._completer.complete()
        else:
            self._completer.popup().hide()

    def show_all(self):
        self._model.setStringList(self.options)
        self.setFocus()
        self._completer.complete()

    def _choose(self, text):
        self.setText(text)
        self.picked.emit(text)

    def _enter(self):
        if self._completer.popup().isVisible():
            return
        matches = ec.filter_options(self.options, self.text())
        if self.value() in self.options:
            self.picked.emit(self.value())
        elif len(matches) == 1:
            self._choose(matches[0])

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Down, Qt.Key_F4) and not self._completer.popup().isVisible():
            self._filter(self.text()) if self.text().strip() else self.show_all()
            return
        super().keyPressEvent(event)


def story_picker_row(picker):
    drop = button("▾", picker.show_all, small=True)
    drop.setToolTip("Mở danh sách truyện")
    return hbox((picker, 1), drop, spacing=2)


class EditorFindBar(FindBar):
    """Thanh tìm & thay dùng chung cho ô Chương và ô Nguồn."""

    def __init__(self, app, edit):
        super().__init__(edit, app)
        self.app = app
        self.select_above_btn = button("⬆️ Chọn Lên", app.select_above_match, "#6a5683", small=True)
        self.select_above_btn.setToolTip("Bôi đen từ đầu Nguồn tới kết quả đang xem (để chuyển sang Chương)")
        self.row.insertWidget(self.row.indexOf(self.close_btn), self.select_above_btn)
        self.replace_entry = LineEdit()
        self.replace_entry.setStyleSheet("font-family: Consolas; font-size: 10pt;")
        self.replace_row = QWidget()
        self.replace_row.setLayout(hbox(label("↪ Thay bằng:", "#d6cebf", 9, True), (self.replace_entry, 1),
                                        button("Thay", app.replace_current, "#3a332c", small=True),
                                        button("Thay tất cả", app.replace_all, ACCENT, small=True),
                                        button("Cả truyện…", app.replace_in_whole_story, "#8a5a22", small=True)))
        self.rows.addWidget(self.replace_row)
        self.replace_row.hide()
        self.replace_entry.returnPressed.connect(app.replace_current)
        QShortcut(QKeySequence("Escape"), self.replace_entry, self.close_bar, context=Qt.WidgetShortcut)

    def close_bar(self):
        self.replace_row.hide()
        super().close_bar()


# ═════════════════════════ Cửa sổ chính ═════════════════════════

class EditorWindow(QWidget):
    def __init__(self, embedded=False):
        super().__init__()
        self.embedded = embedded
        self.loaded_json = None
        self.story_options = []
        self._clean_snapshot = ("", "", "")
        self._loaded_chapter = None   # (story_slug, chapter_id) mở bằng "Mở chương"
        if not embedded:
            self.setWindowTitle("Trình Chỉnh Sửa Chapter & Quản Lý Thư Viện")
            restore_geometry(self, "editor_main", 1300, 750)
        self.setMinimumSize(1040, 640)
        self._flash_timer = QTimer(self, singleShot=True, interval=8000)
        self._flash_timer.timeout.connect(self._reset_status)
        self._count_timer = QTimer(self, singleShot=True, interval=300)
        self._count_timer.timeout.connect(self.update_counter)
        self.setup_ui()
        self.load_story_list()
        self.mark_clean()
        self._last_text = self.temp_text
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        try:
            import r2_store
            from qt_widgets import UiBridge
            self.bridge = UiBridge(self)
            r2_store.add_listener(lambda message, ok: self.bridge.call(self.flash, message, "info" if ok else "error"))
        except ImportError:
            pass

    # ── giao diện ──

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 10)
        root.addWidget(label("THƯ VIỆN  /  BIÊN TẬP", GOLD, 9, True))
        root.addWidget(label("Không gian biên tập", "#f4ede1", 22, True))
        root.addWidget(label("Chọn truyện · Chỉnh sửa nội dung · Phân chương và lưu vào thư viện", MUTED, 10))
        self.find_bar = None
        self.panes = QSplitter(Qt.Horizontal)
        self.panes.setHandleWidth(12)
        self.panes.setChildrenCollapsible(False)
        self.panes.addWidget(self._card(self.build_left))
        self.panes.addWidget(self._card(self.build_right))
        self.find_bar = EditorFindBar(self, self.temp_text)
        root.addSpacing(8)
        root.addWidget(self.find_bar)
        root.addWidget(self.panes, 1)
        self.library_status = label("Thư viện", MUTED, 9)
        root.addLayout(hbox(self.library_status, "stretch",
                            label("Ctrl+S Lưu  •  Ctrl+O Mở JSON  •  Ctrl+F Tìm  •  Ctrl+H Thay thế", "#8a7f70", 9),
                            margins=(0, 6, 0, 0)))
        ctx = Qt.WidgetWithChildrenShortcut
        for keys, slot in (("Ctrl+S", self.save_chapter), ("Ctrl+O", self.pick_json),
                           ("Ctrl+F", lambda: self.show_search()), ("Ctrl+H", lambda: self.show_search(replace=True)),
                           ("F3", lambda: self.find_bar.step(1)), ("Shift+F3", lambda: self.find_bar.step(-1))):
            QShortcut(QKeySequence(keys), self, slot, context=ctx)

    def _card(self, build):
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(f"QFrame#card {{ background: {CARD}; border: 1px solid #3a332c; }}"
                           f"QFrame#card QLabel, QFrame#card QCheckBox {{ background: {CARD}; }}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        build(lay)
        return card

    def _text_edit(self):
        edit = PlainTextEdit()
        edit.setStyleSheet(f"QPlainTextEdit {{ background: {BG}; font-size: 11pt; padding: 8px; }}")
        return edit

    def build_left(self, lay):
        lay.addWidget(label("01   Biên tập chương", "#f4ede1", 14, True))
        lay.addWidget(head("TRUYỆN  ·  Gõ tên hoặc mã để tìm"))
        self.story_combo = StoryPicker()
        self.story_combo.picked.connect(lambda _t: self.on_story_selected())
        row = story_picker_row(self.story_combo)
        row.addWidget(button("+ Truyện mới", self.add_new_story, "#2f2a23", bold=True))
        row.addWidget(button("Xóa truyện", self.delete_story, "#7a322b", bold=True))
        lay.addLayout(row)
        lay.addWidget(head("CHƯƠNG ĐÃ LƯU"))
        self.chap_select_combo = QComboBox()
        self.chap_select_combo.setMaxVisibleItems(20)
        lay.addLayout(hbox((self.chap_select_combo, 1), button("Xóa chương", self.delete_chapter, "#7a322b", bold=True),
                           button("Mở chương", self.load_chapter_for_edit, "#2f2a23", bold=True)))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.addWidget(head("ID KẾ TIẾP"), 0, 0)
        grid.addWidget(head("TÊN CHƯƠNG"), 0, 1)
        self.chap_entry = LineEdit()
        self.chap_entry.setFixedWidth(110)
        self.chap_title_entry = LineEdit()
        grid.addWidget(self.chap_entry, 1, 0)
        grid.addWidget(self.chap_title_entry, 1, 1)
        lay.addLayout(grid)
        self.counter_label = label("", "#8a7f70", 9)
        lay.addLayout(hbox(head("NỘI DUNG"), *self._search_buttons(lambda: self.content_text), "stretch",
                           self.counter_label, margins=(0, 6, 0, 0)))
        self.content_text = self._text_edit()
        lay.addWidget(self.content_text, 1)
        self.content_text.textChanged.connect(self._count_timer.start)
        self.chap_title_entry.textEdited.connect(lambda _t: self._count_timer.start())
        lay.addWidget(button("Lưu chương vào thư viện", self.save_chapter, ACCENT, bold=True))

    def build_right(self, lay):
        lay.addWidget(label("02   Nguồn & phân chương", "#f4ede1", 14, True))
        lay.addWidget(label("Mở bản dịch, chọn nội dung hoặc tách thành nhiều chương.", MUTED, 10))
        grid = QGridLayout()
        for index, (text, slot, primary) in enumerate((
                ("Mở file JSON", self.pick_json, False), ("Phân chương tự động", self.open_split_chapters_dialog, True),
                ("← Chuyển toàn bộ", self.process_json, False), ("← Chuyển phần chọn", self.move_selected_text, False))):
            grid.addWidget(button(text, slot, ACCENT if primary else "#2f2a23", bold=True), index // 2, index % 2)
        lay.addLayout(grid)
        self.temp_status = label("Chưa mở nguồn · Chọn file JSON để bắt đầu", MUTED, 9, wrap=True)
        lay.addWidget(self.temp_status)
        lay.addLayout(hbox(head("NGUỒN"), *self._search_buttons(lambda: self.temp_text), "stretch"))
        self.temp_text = self._text_edit()
        lay.addWidget(self.temp_text, 1)

    def _search_buttons(self, target):
        """Nút Tìm / Thay hiện sẵn cho một ô văn bản (cùng chức năng Ctrl+F / Ctrl+H)."""
        return (button("🔍 Tìm", lambda: self.show_search(target()), small=True),
                button("↪ Thay", lambda: self.show_search(target(), replace=True), small=True))

    def _on_focus_changed(self, _old, new):
        if new in (getattr(self, "temp_text", None), getattr(self, "content_text", None)):
            self._last_text = new

    # ── trạng thái chưa lưu / thông báo ──

    def _editor_snapshot(self):
        return (self.chap_entry.text().strip(), self.chap_title_entry.text().strip(),
                raw_text(self.content_text).strip())

    def mark_clean(self):
        self._clean_snapshot = self._editor_snapshot()
        self.update_counter()

    def is_dirty(self):
        _chap_id, title, content = self._editor_snapshot()
        # Chỉ tên/nội dung chưa lưu mới tính; mã chương điền sẵn không phải công sức người dùng.
        return (title, content) != self._clean_snapshot[1:] and bool(title or content)

    def confirm_discard(self, action):
        """Hỏi trước khi bỏ nội dung chưa lưu. True = tiếp tục."""
        if not self.is_dirty():
            return True
        answer = ask_yes_no_cancel(self, "Nội dung chưa lưu",
                                   f"Chương đang soạn chưa được lưu.\n\nLưu trước khi {action}?\n"
                                   "Có = Lưu rồi tiếp tục · Không = Bỏ thay đổi · Hủy = Quay lại")
        if answer is None:
            return False
        return self.save_chapter() if answer else True

    def flash(self, text, kind="ok"):
        """Thông báo ở chân trang thay cho hộp thoại; tự về trạng thái thường sau 8 giây."""
        set_label(self.library_status, text, FLASH_COLORS.get(kind, MUTED))
        self._flash_timer.start()

    def _reset_status(self):
        set_label(self.library_status, f"{len(self.story_options)} truyện  ·  Mới cập nhật trước", MUTED)

    def update_counter(self):
        dirty = self.is_dirty()
        set_label(self.counter_label, ec.counter_text(raw_text(self.content_text), dirty),
                  "#e8c27a" if dirty else "#8a7f70")

    def _catalog_or_error(self, parent=None):
        """Đọc chặt cho mọi thao tác sẽ ghi list.json. None nếu lỗi."""
        try:
            return read_catalog(ec.CATALOG_PATH)
        except CatalogError as exc:
            error(parent or self, "Không đọc được danh mục", f"{exc}\n\nĐã dừng để không ghi đè mất danh sách truyện.")
            return None

    def _read_chapter_catalog(self):
        """Đọc dễ dãi, chỉ để hiển thị."""
        try:
            return read_catalog(ec.CATALOG_PATH)
        except CatalogError:
            return []

    def next_chapter_id(self, story_slug, catalog=None):
        if not story_slug:
            return store.format_chapter_id(1)
        return store.next_chapter_id(self._read_chapter_catalog() if catalog is None else catalog, story_slug)

    # ── danh sách truyện / chương ──

    def load_story_list(self):
        ec.ensure_catalog()
        self.story_options = []
        try:
            self.story_options = ec.story_options(read_catalog(ec.CATALOG_PATH))
        except CatalogError as exc:
            error(self, "Không đọc được danh mục",
                  f"{exc}\n\nTrình biên tập sẽ không ghi vào list.json cho tới khi file được sửa.")
        self.story_combo.set_options(self.story_options)
        self._reset_status()

    def current_story_slug(self):
        value = self.story_combo.value()
        return ec.split_option(value)[0] if value else ""

    def on_story_selected(self):
        story_value = self.story_combo.value()
        if not story_value:
            return
        story_slug = ec.split_option(story_value)[0]
        self.chap_entry.setText(self.next_chapter_id(story_slug))
        self._refresh_chap_select(story_slug)

    def _refresh_chap_select(self, story_slug, catalog=None, selected_id=None):
        options = ec.chapter_options(self._read_chapter_catalog() if catalog is None else catalog, story_slug)
        self.chap_select_combo.clear()
        self.chap_select_combo.addItems(options)
        index = next((i for i, o in enumerate(options) if o.split("|", 1)[0].strip() == selected_id), -1)
        self.chap_select_combo.setCurrentIndex(index)

    def _sync_saved_chapters(self, story_slug, catalog, selected_id):
        """Cập nhật theo danh mục vừa lưu, không đọc lại đĩa."""
        self.story_options = ec.story_options(catalog)
        self.story_combo.set_options(self.story_options)
        self._reset_status()
        self.story_combo.setText(next((o for o in self.story_options if o.split("|", 1)[0].strip() == story_slug), ""))
        self._refresh_chap_select(story_slug, catalog, selected_id)
        self.chap_entry.setText(self.next_chapter_id(story_slug, catalog))

    def delete_story(self):
        story_value = self.story_combo.value()
        if not self.story_combo.is_valid():
            warn(self, "Chú ý", "Vui lòng chọn truyện trong danh sách!")
            return
        story_slug, story_title = ec.split_option(story_value)
        if not ask_yes_no(self, "Xóa truyện", f"Xóa truyện {story_title} cùng toàn bộ chương đã lưu?\n\n"
                                              "Dữ liệu truyện sẽ bị xóa khỏi thư viện.", default_no=True, warning=True):
            return
        try:
            catalog, cleanup_warning = ec.delete_library_story(story_slug)
        except Exception as exc:
            error(self, "Lỗi", f"Không thể xóa truyện:\n{exc}")
            return
        self.story_options = ec.story_options(catalog)
        self.story_combo.set_options(self.story_options)
        self.story_combo.clear()
        self.chap_select_combo.clear()
        self.chap_entry.setText(store.format_chapter_id(1))
        # Chỉ xoá ô soạn nếu nó đang chứa chương của truyện vừa xoá.
        if self._loaded_chapter and self._loaded_chapter[0] == story_slug:
            self.chap_title_entry.clear()
            self.content_text.clear()
            self._loaded_chapter = None
            self.mark_clean()
        if cleanup_warning:
            warn(self, "Đã xóa truyện", cleanup_warning)
        else:
            self.flash(f"🗑 Đã xóa truyện: {story_title}")

    def delete_chapter(self):
        story_value = self.story_combo.value()
        chap_value = self.chap_select_combo.currentText().strip()
        if not self.story_combo.is_valid():
            warn(self, "Chú ý", "Vui lòng chọn truyện trong danh sách!")
            return
        if not chap_value:
            warn(self, "Chú ý", "Vui lòng chọn chương muốn xóa!")
            return
        story_slug = ec.split_option(story_value)[0]
        chap_slug = chap_value.split("|", 1)[0].strip()
        if not ask_yes_no(self, "Xóa chương", f"Xóa chương {chap_value} khỏi truyện {story_value}?\n\n"
                                              "Dữ liệu chương sẽ bị xóa khỏi thư viện. Nếu đang biên tập chương này, "
                                              "nội dung chưa lưu cũng sẽ bị xóa.", default_no=True, warning=True):
            return
        try:
            catalog, cleanup_warning = ec.delete_library_chapter(story_slug, chap_slug)
        except Exception as exc:
            error(self, "Lỗi", f"Không thể xóa chương:\n{exc}")
            return
        if self.chap_entry.text().strip() == chap_slug:
            self.chap_title_entry.clear()
            self.content_text.clear()
            self.chap_entry.setText(self.next_chapter_id(story_slug, catalog))
            self._loaded_chapter = None
            self.mark_clean()
        elif not self.chap_title_entry.text().strip() and not raw_text(self.content_text).strip():
            self.chap_entry.setText(self.next_chapter_id(story_slug, catalog))
        self._refresh_chap_select(story_slug, catalog)
        if cleanup_warning:
            warn(self, "Đã xóa chương", cleanup_warning)
        else:
            self.flash(f"🗑 Đã xóa chương: {chap_value}")

    def load_chapter_for_edit(self):
        if not self.confirm_discard("mở chương khác"):
            return
        story_value = self.story_combo.value()
        chap_value = self.chap_select_combo.currentText().strip()
        if not story_value:
            warn(self, "Chú ý", "Vui lòng chọn Truyện trước!")
            return
        if not chap_value:
            warn(self, "Chú ý", "Vui lòng chọn Chương muốn sửa!")
            return
        story_slug = ec.split_option(story_value)[0]
        chap_slug = chap_value.split("|", 1)[0].strip()
        try:
            chap_title, paragraphs = ec.read_library_chapter(story_slug, chap_slug)
        except Exception as exc:
            error(self, "Lỗi", f"Không thể đọc chương:\n{exc}")
            return
        self.chap_entry.setText(chap_slug)
        self.chap_title_entry.setText(chap_title)
        self.content_text.setPlainText("\n\n".join(paragraphs))   # setPlainText xoá lịch sử hoàn tác
        self._loaded_chapter = (story_slug, chap_slug)
        self.mark_clean()
        self.flash(f"📖 Đang sửa chương {chap_value} — Ctrl+S để lưu đè.", "info")

    def add_new_story(self):
        default_title = (self.loaded_json or {}).get("title", "")
        dlg = QDialog(self)
        dlg.setWindowTitle("Thêm Truyện Mới")
        restore_geometry(dlg, "editor_add_story_dialog", 480, 170)
        lay = QVBoxLayout(dlg)
        lay.addWidget(label("➕ Thêm Truyện Mới", "#f4ede1", 11, True))
        lay.addWidget(label("Tên hiển thị của truyện:", MUTED, 9))
        entry = LineEdit(default_title)
        entry.selectAll()
        lay.addWidget(entry)
        lay.addWidget(label("ID sẽ được tạo tự động.", HINT, 9))
        lay.addLayout(hbox("stretch", button("✅ Tạo Truyện", dlg.accept, ACCENT, bold=True), button("Hủy", dlg.reject)))
        entry.returnPressed.connect(dlg.accept)
        accepted = dlg.exec() == QDialog.Accepted
        save_geometry(dlg, "editor_add_story_dialog")
        title = entry.text().strip()
        if not accepted or not title:
            return
        catalog = self._catalog_or_error()
        if catalog is None:
            return
        try:
            slug = ec.add_story(catalog, title)
        except Exception as exc:
            error(self, "Lỗi", f"Không thể lưu list.json:\n{exc}")
            return
        self.load_story_list()
        self.flash(f"➕ Đã tạo truyện {slug} | {title}  (thư mục library/{slug})")
        new_item = f"{slug} | {title}"
        if new_item in self.story_options:
            self.story_combo.setText(new_item)
            self.on_story_selected()

    # ── lưu ──

    def save_chapter(self):
        """Lưu chương đang soạn. True khi đã ghi."""
        story_value = self.story_combo.value()
        if story_value and not self.story_combo.is_valid():
            warn(self, "Chọn truyện", "Hãy chọn một truyện trong danh sách gợi ý trước khi lưu.")
            return False
        chap_slug = self.chap_entry.text().strip()
        chap_title = self.chap_title_entry.text().strip() or "Oneshot"
        content = raw_text(self.content_text).strip()
        if not story_value:
            warn(self, "Chú ý", "Vui lòng chọn Truyện!")
            return False
        if not content:
            warn(self, "Chú ý", "Nội dung chương không được để trống!")
            return False
        story_slug, story_title = ec.split_option(story_value)
        catalog = self._catalog_or_error()
        if catalog is None:
            return False
        chap_slug = ec.slugify_vn(chap_slug) if chap_slug else self.next_chapter_id(story_slug, catalog)
        # Ghi đè chương có sẵn chỉ khi chính chương đó đang được mở để sửa.
        if ec.chapter_exists(catalog, story_slug, chap_slug) and self._loaded_chapter != (story_slug, chap_slug):
            if not ask_yes_no(self, "Ghi đè chương?", f"Chương {chap_slug} đã có trong truyện này.\n"
                                                      "Ghi đè nội dung chương đó?", default_no=True, warning=True):
                return False
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        try:
            catalog, _slug, _saved = store.save_chapters(
                ec.LIBRARY_DIR, ec.BASE_DIR, ec.CATALOG_PATH, story_slug, story_title,
                [(chap_slug, chap_title, (("", p) for p in paragraphs))], overwrite=True)
        except Exception as exc:
            error(self, "Lỗi", f"Không thể lưu chương:\n{exc}")
            return False
        self._sync_saved_chapters(story_slug, catalog, chap_slug)
        # Dọn ô soạn và điền sẵn mã chương tiếp theo
        self.chap_title_entry.clear()
        self.content_text.clear()
        self._loaded_chapter = None
        self.mark_clean()
        self.flash(f"✅ Đã lưu chương {chap_slug} · {chap_title} ({len(paragraphs)} đoạn)")
        return True

    # ── nguồn ──

    def pick_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn data.json", ec.LIBRARY_DIR, "JSON files (*.json)")
        if not path:
            return
        try:
            src = ec.read_source_json(path)
        except Exception:
            error(self, "Lỗi", "Không thể đọc file JSON.")
            return
        self.loaded_json = src["json"]
        self.temp_text.setPlainText(src["text"])
        title, chap_title = src["title"], src["chapter_title"]
        story_slug, chap_slug = src["story_slug"], src["chapter_slug"]
        # Đang soạn dở thì không đụng vào truyện/ID/tên chương của ô soạn.
        if self.is_dirty():
            story_slug = ""
        if story_slug and chap_slug and story_slug.lower() not in ("stories", "library"):
            # library/<truyện>/<chương>/data.json
            found = next((o for o in self.story_options if o.startswith(f"{story_slug} |")), None)
            self.story_combo.setText(found or f"{story_slug} | {title}")
            self.chap_entry.setText(chap_slug)
            if chap_title:
                self.chap_title_entry.setText(chap_title)
        elif story_slug.lower() == "stories":
            # stories/<truyện>/data.json (do builder tạo): tìm truyện cùng tên trong thư viện
            found = next((o for o in self.story_options
                          if "|" in o and o.split("|", 1)[1].strip().lower() == title.strip().lower()), None)
            if found:
                self.story_combo.setText(found)
                self.chap_entry.setText(self.next_chapter_id(found.split("|")[0].strip()))
            if chap_title:
                self.chap_title_entry.setText(chap_title)
        set_label(self.temp_status, f"Đã nạp: {os.path.basename(path)} | Truyện: {title} | "
                                    f"Chương: {chap_title or 'Chưa rõ'} | {src['count']} đoạn", GOLD)

    def process_json(self):
        new_text = raw_text(self.temp_text).strip()
        if not new_text:
            warn(self, "Chú ý", "Cửa sổ temp đang trống hoặc chưa có nội dung.")
            return
        self.loaded_json = self.loaded_json or {}
        if raw_text(self.content_text).strip():
            choice = ask_yes_no_cancel(self, "Editor đang có nội dung",
                                       "Có = Viết tiếp xuống dưới\nKhông = Thay thế toàn bộ nội dung đang có\n"
                                       "Hủy = Không làm gì")
            if choice is None:
                return
            cursor = self.content_text.textCursor()
            if choice:
                cursor.movePosition(QTextCursor.End)
                cursor.insertText("\n\n" + new_text)
            else:
                cursor.select(QTextCursor.Document)
                cursor.insertText(new_text)
        else:
            self.content_text.setPlainText(new_text)
        # Tên chương còn trống: lấy chapter_title trong JSON, không có thì tên truyện.
        if not self.chap_title_entry.text().strip():
            story_value = self.story_combo.value()
            selected_title = ec.split_option(story_value)[1] if story_value else ""
            title = (self.loaded_json.get("chapter_title", "").strip() or self.loaded_json.get("title", "").strip()
                     or selected_title)
            if title:
                self.chap_title_entry.setText(title)

    def move_selected_text(self):
        picked = selected_text(self.temp_text)
        if not picked.strip():
            warn(self, "Chú ý", "Vui lòng bôi đen (chọn) phần văn bản cần chuyển trong cửa sổ bên phải.")
            return
        # Tên chương trống mà dòng đầu có chữ "Chương" thì lấy làm tên.
        if not self.chap_title_entry.text().strip():
            first_line = picked.strip().split("\n")[0].strip()
            if re.search(r"chương", first_line, re.IGNORECASE):
                self.chap_title_entry.setText(first_line)
        self.temp_text.textCursor().removeSelectedText()
        cursor = self.content_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(("\n\n" if raw_text(self.content_text).strip() else "") + picked)

    # ── tìm & thay ──

    def show_search(self, target=None, replace=False):
        target = target or self._last_text or self.temp_text
        bar = self.find_bar
        bar.set_edit(target)
        is_source = target is self.temp_text
        bar.where.setText("🔍 Nguồn:" if is_source else "🔍 Chương:")
        bar.select_above_btn.setVisible(is_source)
        if replace:
            bar.replace_row.show()
        bar.open_bar()
        if replace and bar.entry.text():
            bar.replace_entry.setFocus()
            bar.replace_entry.selectAll()

    def _pattern_or_flash(self):
        try:
            return self.find_bar.pattern()
        except (re.error, ValueError) as exc:
            self.flash(f"Regex lỗi: {exc}", "error")
            return None

    def _replacement_for(self, match):
        text = self.find_bar.replace_entry.text()
        return match.expand(text) if self.find_bar.regex.isChecked() else text

    def replace_current(self):
        bar, edit = self.find_bar, self.find_bar.edit
        pattern = self._pattern_or_flash()
        current = bar.current()
        if pattern is None or current is None:
            bar.refresh()
            return
        text = raw_text(edit)
        match = pattern.match(text, py_offset(text, current[0]))
        if not match:
            bar.refresh()
            return
        try:
            new_text = self._replacement_for(match)
        except (re.error, IndexError) as exc:
            self.flash(f"Chuỗi thay thế lỗi: {exc}", "error")
            return
        cursor = QTextCursor(edit.document())
        cursor.setPosition(current[0])
        cursor.setPosition(current[1], QTextCursor.KeepAnchor)
        cursor.insertText(new_text)   # một bước Ctrl+Z
        bar.refresh(anchor=current[0] + qt_offsets(new_text)(len(new_text)))

    def replace_all(self):
        edit = self.find_bar.edit
        pattern = self._pattern_or_flash()
        if pattern is None:
            return
        try:
            new_text, count = pattern.subn(self._replacement_for, raw_text(edit))
        except (re.error, IndexError, ValueError) as exc:
            self.flash(f"Lỗi thay thế: {exc}", "error")
            return
        if not count:
            self.flash("Không có chỗ nào khớp để thay.", "warn")
            return
        cursor = QTextCursor(edit.document())
        cursor.select(QTextCursor.Document)
        cursor.insertText(new_text)   # một bước Ctrl+Z
        self.find_bar.refresh()
        self.flash(f"↪ Đã thay {count} chỗ trong {'Nguồn' if edit is self.temp_text else 'Chương'} (Ctrl+Z để hoàn tác).")

    def select_above_match(self):
        """Bôi đen từ đầu Nguồn tới trước kết quả đang xem."""
        current = self.find_bar.current()
        if current is None:
            return
        edit = self.find_bar.edit
        cursor = QTextCursor(edit.document())
        cursor.setPosition(current[0])
        cursor.setPosition(0, QTextCursor.KeepAnchor)
        edit.setTextCursor(cursor)
        edit.setFocus()

    def replace_in_whole_story(self):
        """Thay trong mọi chương đã lưu của truyện đang chọn (có sao lưu)."""
        if not self.story_combo.is_valid():
            warn(self, "Chọn truyện", "Chọn truyện ở ô TRUYỆN bên trái trước.")
            return
        story_slug, story_title = ec.split_option(self.story_combo.value())
        try:
            pattern = self.find_bar.pattern()
        except (re.error, ValueError) as exc:
            error(self, "Regex lỗi", str(exc))
            return
        if pattern is None:
            warn(self, "Chú ý", "Nhập nội dung cần tìm trước.")
            return
        if self._loaded_chapter and self._loaded_chapter[0] == story_slug and self.is_dirty():
            warn(self, "Chương chưa lưu", "Chương của truyện này đang mở và chưa lưu. "
                                          "Hãy lưu (Ctrl+S) hoặc bỏ thay đổi trước.")
            return
        catalog = self._catalog_or_error()
        if catalog is None:
            return
        replacement = self.find_bar.replace_entry.text()
        regex = self.find_bar.regex.isChecked()
        query = self.find_bar.entry.text()
        try:
            preview = store.replace_in_story(ec.LIBRARY_DIR, catalog, story_slug, pattern, replacement, regex=regex)
        except Exception as exc:
            error(self, "Lỗi", f"Không quét được truyện:\n{exc}")
            return
        if not preview["total"]:
            self.flash(f"Không tìm thấy \"{query}\" trong truyện {story_title}.", "warn")
            return
        sample = ", ".join(f"{cid} ({n})" for cid, n in preview["chapters"][:8])
        more = "…" if len(preview["chapters"]) > 8 else ""
        if not ask_yes_no(self, "Thay trong cả truyện",
                          f"Thay {preview['total']} chỗ trong {len(preview['chapters'])} chương của \"{story_title}\"?\n\n"
                          f"\"{query}\" → \"{replacement}\"\n\nChương: {sample}{more}\n\n"
                          "Bản data.json cũ được sao lưu vào thư mục .backups.", default_no=True, warning=True):
            return
        try:
            result = store.replace_in_story(ec.LIBRARY_DIR, catalog, story_slug, pattern, replacement,
                                            regex=regex, apply=True, backup_root=ec.BACKUP_DIR)
            write_catalog(ec.CATALOG_PATH, catalog)
        except Exception as exc:
            error(self, "Lỗi", f"Thay thế bị dừng giữa chừng:\n{exc}\n\nBản sao lưu nằm trong {ec.BACKUP_DIR}.")
            return
        # Chương đang mở (chưa sửa) giờ khác trên đĩa: áp cùng thay đổi vào ô soạn.
        if self._loaded_chapter and self._loaded_chapter[0] == story_slug:
            if self._loaded_chapter[1] in {cid for cid, _n in result["chapters"]}:
                self.content_text.setPlainText(pattern.sub(self._replacement_for, raw_text(self.content_text)))
                self.chap_title_entry.setText(pattern.sub(self._replacement_for, self.chap_title_entry.text()))
                self.mark_clean()
        current = self.chap_select_combo.currentText().split("|", 1)[0].strip() or None
        self._refresh_chap_select(story_slug, catalog, current)
        self.find_bar.refresh()
        self.flash(f"↪ Đã thay {result['total']} chỗ trong {len(result['chapters'])} chương · sao lưu: {result['backup']}")

    # ── phân chương ──

    def open_split_chapters_dialog(self):
        if not raw_text(self.temp_text).strip():
            warn(self, "Chú ý", "Cửa sổ bên phải đang trống. Hãy load file JSON trước!")
            return
        SplitDialog(self).exec()

    def save_split_chapters(self, dlg, story_value, chapters):
        """Lưu các chương đã tách. True khi đã lưu."""
        if story_value and story_value not in self.story_options:
            warn(dlg, "Chọn truyện", "Hãy chọn một truyện trong danh sách gợi ý trước khi lưu.")
            return False
        if not story_value:
            warn(dlg, "Chú ý", "Vui lòng chọn Truyện!")
            return False
        if not chapters:
            warn(dlg, "Chú ý", "Không có chương nào để lưu!")
            return False
        story_slug, story_title = ec.split_option(story_value)
        empty = [ch for ch in chapters if not ch["paragraphs"]]
        if empty:
            names = ", ".join(ch["title"][:30] for ch in empty[:3])
            if not ask_yes_no(dlg, "Chú ý", f"{len(empty)} chương không có nội dung ({names}...).\n"
                                            "Bạn vẫn muốn lưu các chương có nội dung?"):
                return False
        catalog = self._catalog_or_error(parent=dlg)
        if catalog is None:
            return False
        clashes = [ch["id"] for ch in chapters if ch["paragraphs"] and ec.chapter_exists(catalog, story_slug, ch["id"])]
        if clashes and not ask_yes_no(dlg, "Ghi đè chương?", f"{len(clashes)} chương đã tồn tại "
                                                             f"({', '.join(clashes[:5])}...).\nGhi đè các chương này?",
                                      default_no=True, warning=True):
            return False
        items = [(ch["id"], ch["title"].strip() or f"Chương {ch['id']}", (("", p) for p in ch["paragraphs"]))
                 for ch in chapters if ch["paragraphs"]]
        try:
            catalog, _slug, saved_ids = store.save_chapters(
                ec.LIBRARY_DIR, ec.BASE_DIR, ec.CATALOG_PATH, story_slug, story_title, items, overwrite=True)
        except Exception as exc:
            error(dlg, "Lỗi", f"Không thể lưu chương:\n{exc}")
            return False
        if saved_ids:
            self._sync_saved_chapters(story_slug, catalog, saved_ids[-1])
        self.flash(f"✅ Đã lưu {len(saved_ids)} chương vào truyện '{story_title}'")
        return True

    # ── đóng ──

    def can_close(self):
        return self.confirm_discard("thoát")

    def closeEvent(self, event):
        if not self.can_close():
            event.ignore()
            return
        if not self.embedded:
            save_geometry(self, "editor_main")
        super().closeEvent(event)


class SplitDialog(QDialog):
    """🔪 Phân chương tự động: chọn/gộp mẫu tiêu đề, xem & sửa tên, tách/gộp mốc, lưu."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("🔪 Phân Chương Tự Động")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        restore_geometry(self, "editor_split_dialog", 900, 700)
        self.setMinimumSize(700, 560)
        self.patterns = ec.get_split_patterns()
        self.chapters = []    # [{"id", "original_title", "title", "paragraphs"}]
        self.preview_index = None
        self._build()
        self.run_detect()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.addWidget(label("🔪 Phân Chương Tự Động", "#f4ede1", 12, True))
        lay.addWidget(head("BƯỚC 1 — Chọn pattern nhận diện header chương:"))
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems([n for n, _ in self.patterns])
        self.pattern_combo.setMinimumWidth(220)
        self.regex_entry = LineEdit(self.patterns[0][1])
        self.regex_entry.setStyleSheet("font-family: Consolas; font-size: 9pt;")
        lay.addLayout(hbox(self.pattern_combo, (self.regex_entry, 1),
                           button("➕ Gộp", self.combine_selected_pattern, "#5c4a73", small=True),
                           button("💾 Lưu pattern", self.save_custom_pattern, "#3a332c", small=True)))
        self.match_label = label("Chọn pattern rồi bấm ➕ Gộp để quét cùng lúc nhiều kiểu tiêu đề chương.", "#8a7f70", 9)
        lay.addWidget(self.match_label)
        self.pattern_combo.activated.connect(lambda i: self.regex_entry.setText(self.patterns[i][1]))
        self.regex_entry.returnPressed.connect(self.run_detect)

        self.count_label = head("BƯỚC 2 — Xem & chỉnh sửa tên chương:")
        lay.addLayout(hbox(self.count_label, "stretch",
                           button("Xóa mốc (gộp vào chương trước)", self.remove_boundary, "#3a2420", fg="#f0a99f", small=True),
                           button("🔍 Phân tích lại", self.run_detect, "#6a5683", small=True, bold=True), margins=(0, 8, 0, 0)))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "ID", "Tên chương (bấm đúp để sửa)", "Đoạn"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for col, width in ((0, 46), (1, 80), (3, 64)):
            self.table.setColumnWidth(col, width)
        self.table.setStyleSheet(f"QTableWidget {{ background: {PANEL}; alternate-background-color: #221e19; "
                                 f"selection-background-color: #5a4320; gridline-color: {BG}; }}")
        self.table.currentCellChanged.connect(lambda row, _c, _pr, _pc: self.show_preview(row if row >= 0 else None))
        self.table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.table, 3)

        self.preview_label = head("XEM TRƯỚC — chọn một dòng ở bảng")
        self.split_btn = button("✂ Tách chương tại đoạn có con trỏ", self.split_at_cursor, ACCENT, small=True, bold=True)
        self.split_btn.setEnabled(False)
        lay.addLayout(hbox(self.preview_label, "stretch", self.split_btn, margins=(0, 6, 0, 0)))
        self.preview = PlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(f"QPlainTextEdit {{ background: {BG}; color: #d6cebf; font-size: 10pt; }}")
        self.preview.cursorPositionChanged.connect(self._highlight_paragraph)
        lay.addWidget(self.preview, 2)

        lay.addWidget(head("BƯỚC 3 — Chọn truyện để lưu:"))
        self.story = StoryPicker(self.app.story_options)
        if self.app.story_combo.is_valid():
            self.story.setText(self.app.story_combo.value())
        self.story.picked.connect(lambda _t: self.change_story())
        self.save_btn = button("💾 Lưu tất cả (0 chương)", self.save_all, "#6a5683", bold=True)
        lay.addLayout(story_picker_row(self.story))
        lay.addLayout(hbox("stretch", self.save_btn, button("Hủy", self.reject), margins=(0, 6, 0, 0)))

    def done(self, code):
        save_geometry(self, "editor_split_dialog")
        super().done(code)

    def pattern_label(self, part):
        """Tên mẫu có sẵn cho một nhánh của regex, không có thì chính regex."""
        return next((name for name, rx in self.patterns if rx == part), part if len(part) <= 28 else part[:27] + "…")

    def combine_selected_pattern(self):
        rx = self.patterns[self.pattern_combo.currentIndex()][1]
        self.regex_entry.setText(store.combine_patterns(self.regex_entry.text().strip(), rx))
        self.run_detect()

    def save_custom_pattern(self):
        rx = self.regex_entry.text().strip()
        if not rx:
            return
        existing = next((n for n, r in self.patterns if r == rx), None)
        if existing:
            info(self, "Đã có", f"Pattern này đã có trong danh sách: '{existing}'.")
            return
        parts = store.split_alternatives(rx)
        if len(parts) > 1 and all(any(r == part for _n, r in self.patterns) for part in parts):
            name = " + ".join(self.pattern_label(part) for part in parts)
        else:
            name = f"Tuỳ chỉnh: {rx[:20]}"
        ec.save_split_pattern(name, rx)
        self.patterns.append((name, rx))
        self.pattern_combo.addItem(name)
        self.pattern_combo.setCurrentIndex(len(self.patterns) - 1)
        info(self, "Đã lưu", f"Pattern '{name}' đã được lưu vào config.")

    def start_id(self):
        value = self.story.value()
        slug = ec.split_option(value)[0] if "|" in value else ""
        try:
            return int(self.app.next_chapter_id(slug) if slug else store.format_chapter_id(1))
        except ValueError:
            return 1

    def run_detect(self):
        rx = self.regex_entry.text().strip()
        if not rx:
            warn(self, "Chú ý", "Vui lòng nhập regex pattern!")
            return
        try:
            re.compile(rx, re.IGNORECASE)
        except re.error as exc:
            error(self, "Regex lỗi", str(exc))
            return
        found = ec.detect_chapters(raw_text(self.app.temp_text).strip(), rx)
        start = self.start_id()
        self.chapters = [{"id": store.format_chapter_id(start + i), "original_title": ch["title"],
                          "title": ch["title"] or f"Chương {start + i}", "paragraphs": ch["paragraphs"]}
                         for i, ch in enumerate(found)]
        counts = ec.pattern_counts(found, rx)
        if counts:
            set_label(self.match_label, "Khớp:  " + "  ·  ".join(f"{self.pattern_label(p)}: {n}" for p, n in counts.items()),
                      GOLD)
        else:
            set_label(self.match_label, "Chọn pattern rồi bấm ➕ Gộp để quét cùng lúc nhiều kiểu tiêu đề chương.", "#8a7f70")
        self.build_table()
        self.show_preview(None)

    def build_table(self, select=None):
        n = len(self.chapters)
        set_label(self.count_label, f"BƯỚC 2 — Xem & chỉnh sửa ({n} chương phát hiện):" if n else
                  "BƯỚC 2 — Không phát hiện được chương nào với pattern này.", GOLD if n else ERROR)
        self.save_btn.setText(f"💾 Lưu tất cả ({n} chương)")
        self.table.blockSignals(True)
        self.table.setRowCount(n)
        for i, chap in enumerate(self.chapters):
            cells = (str(i + 1), chap["id"], chap["title"], str(len(chap["paragraphs"])))
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col != 2:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignCenter)
                if col in (1, 3):
                    item.setForeground(QColor(GOLD))
                elif col == 0:
                    item.setForeground(QColor(HINT))
                self.table.setItem(i, col, item)
        self.table.blockSignals(False)
        if select is not None and 0 <= select < n:
            self.table.setCurrentCell(select, 2)

    def _on_item_changed(self, item):
        if item.column() == 2 and 0 <= item.row() < len(self.chapters):
            self.chapters[item.row()]["title"] = item.text()
            if item.row() == self.preview_index:
                self._update_preview_label()

    def _update_preview_label(self):
        chap = self.chapters[self.preview_index]
        self.preview_label.setText(f"XEM TRƯỚC #{self.preview_index + 1} · {chap['id']} · {chap['title'][:40]}")

    def show_preview(self, index):
        if index is None or not 0 <= index < len(self.chapters):
            self.preview_index = None
            self.preview.clear()
            self.preview_label.setText("XEM TRƯỚC — chọn một dòng ở bảng")
            self.split_btn.setEnabled(False)
            return
        self.preview_index = index
        chap = self.chapters[index]
        self._update_preview_label()
        self.preview.setPlainText("\n".join(f"[{n + 1}] {p}" for n, p in enumerate(chap["paragraphs"])))
        self.preview.moveCursor(QTextCursor.Start)
        self.split_btn.setEnabled(len(chap["paragraphs"]) > 1)

    def _highlight_paragraph(self):
        sel = QTextEdit.ExtraSelection()
        sel.cursor = self.preview.textCursor()
        sel.cursor.clearSelection()
        sel.format.setBackground(QColor("#3a2f1f"))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        self.preview.setExtraSelections([sel])

    def renumber(self):
        if self.chapters:
            start = int(self.chapters[0]["id"])
            for offset, chapter in enumerate(self.chapters):
                chapter["id"] = store.format_chapter_id(start + offset)

    def split_at_cursor(self):
        if self.preview_index is None:
            return
        chap = self.chapters[self.preview_index]
        index = self.preview.textCursor().blockNumber()
        if index <= 0 or index >= len(chap["paragraphs"]):
            info(self, "Tách chương", "Đặt con trỏ vào một đoạn (không phải đoạn đầu tiên) để làm tên chương mới.")
            return
        header = chap["paragraphs"][index]
        self.chapters.insert(self.preview_index + 1, {"id": chap["id"], "original_title": header,
                                                      "title": header[:120], "paragraphs": chap["paragraphs"][index + 1:]})
        chap["paragraphs"] = chap["paragraphs"][:index]
        self.renumber()
        self.build_table(select=self.preview_index + 1)

    def remove_boundary(self):
        index = self.table.currentRow()
        if index <= 0 or index >= len(self.chapters):
            info(self, "Xóa mốc", "Chọn một chương (không phải chương đầu) để gộp vào chương trước nó.")
            return
        removed = self.chapters.pop(index)
        previous = self.chapters[index - 1]
        # Trả tiêu đề gốc về làm đoạn văn, không dùng tên đã sửa để hiển thị.
        if removed["original_title"]:
            previous["paragraphs"].append(removed["original_title"])
        previous["paragraphs"].extend(removed["paragraphs"])
        self.renumber()
        self.build_table(select=index - 1)
        self.show_preview(index - 1)

    def change_story(self):
        # Đổi truyện đích không được khôi phục mốc/tên đã xoá: chỉ đánh lại mã.
        start = self.start_id()
        for offset, chapter in enumerate(self.chapters):
            chapter["id"] = store.format_chapter_id(start + offset)
        self.build_table(select=self.table.currentRow())

    def save_all(self):
        if self.app.save_split_chapters(self, self.story.value(), self.chapters):
            self.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = EditorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
