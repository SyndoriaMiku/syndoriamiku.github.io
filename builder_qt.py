"""Story Translator (bản Qt / PySide6): dịch truyện Trung → Việt, Review, Lưu vào thư viện, Scan Names.

Thay builder.py (Tk) — Qt hiển thị chữ đang gõ bằng bộ gõ IME (EVKey chế độ IME, Pinyin…) ngay
trong ô, không bật khung preview riêng. Phần xử lý dùng chung: translator_core.py.

Chạy: python builder_qt.py
"""
import os
import re
import sys
import threading
import time
import unicodedata

# Console Windows (cp1252) không in được tiếng Việt: print() sẽ ném UnicodeEncodeError giữa chừng.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PySide6.QtCore import QEasingCurve, QEvent, QItemSelectionModel, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QKeySequence, QShortcut, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMenu,
                               QProgressBar, QRadioButton, QSpinBox, QTextEdit, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

import library_store as store
import r2_store
import translator_core as core
from library_store import CatalogError, read_catalog
from editor_core import search_key
from qt_widgets import (ACCENT, ERROR, HINT, OK_GREEN, STYLE, WARN, FindBar, LineEdit, PlainTextEdit, UiBridge,
                        ask_yes_no, ask_yes_no_cancel, button, error, info, label, qt_offsets, raw_text,
                        restore_geometry, save_geometry, selected_text, set_label, warn)
from translator_core import BG, FIELD, MUTED, PANEL, TEXT, BASE_DIR, LIBRARY_CATALOG, LIBRARY_DIR, STORIES_DIR

CN_FONT = "Microsoft YaHei UI"


def hbox(*items, margins=(0, 0, 0, 0), spacing=6):
    row = QHBoxLayout()
    row.setContentsMargins(*margins)
    row.setSpacing(spacing)
    for item in items:
        if item == "stretch":
            row.addStretch(1)
        elif isinstance(item, tuple):
            row.addWidget(item[0], item[1])
        elif isinstance(item, QWidget):
            row.addWidget(item)
        else:
            row.addLayout(item)
    return row


# ═════════════════════════ Review ═════════════════════════

class _PairHighlighter(QSyntaxHighlighter):
    """Tô màu theo dòng: 3 dòng một đoạn — Trung (xám), Việt (sáng), dòng trống."""

    def __init__(self, doc):
        super().__init__(doc)
        self.cn, self.vi = QTextCharFormat(), QTextCharFormat()
        self.cn.setForeground(QColor("#8a7f70"))
        self.cn.setFont(QFont(CN_FONT, 11))
        self.vi.setForeground(QColor("#f4ede1"))

    def highlightBlock(self, text):
        offset = self.currentBlock().blockNumber() % 3
        if offset == 0:
            self.setFormat(0, len(text), self.cn)
        elif offset == 1:
            self.setFormat(0, len(text), self.vi)


class ReviewWindow(QWidget):
    def __init__(self, app, title, slug, cn_lines, vi_lines, from_draft=False):
        super().__init__(app, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(f"Review & Edit Name: {title}")
        self.app = app
        self.title = title
        self.slug = slug
        self.cn_lines = cn_lines
        self.vi_lines = vi_lines
        self.saved = False             # đã lưu data.json hoặc vào thư viện
        self._saved_data_once = False  # đã ghi stories/<slug>/data.json trong phiên này
        self._closing_ok = False
        self._draft_timer = QTimer(self, singleShot=True, interval=1500)
        self._draft_timer.timeout.connect(self.save_draft)
        restore_geometry(self, "builder_review", 900, 700)
        self.setup_ui()
        self.load_content()
        app.reviews.append(self)
        if from_draft:
            self.set_status(f"📝 Đã mở nháp: {len(cn_lines)} đoạn — chưa lưu", WARN)
        else:
            self.save_draft()
        self.show()

    # ── nháp & trạng thái ──

    def set_status(self, text, color=OK_GREEN):
        set_label(self.status_lbl, text, color)

    def mark_changed(self):
        self.saved = False
        self._draft_timer.start()

    def save_draft(self):
        self._draft_timer.stop()
        try:
            core.write_draft(self.title, self.slug, self.cn_lines, self.vi_lines)
            self.set_status(f"📝 Nháp tự lưu lúc {time.strftime('%H:%M:%S')} — .drafts/{self.slug}.json",
                            "#8a7f70" if self.saved else WARN)
        except Exception as exc:
            self.set_status(f"⚠ Không lưu được nháp: {exc}", ERROR)

    def _finish_close(self):
        self._draft_timer.stop()
        save_geometry(self, "builder_review")
        if self.saved:
            core.remove_draft(self.slug)
        else:
            self.save_draft()
        self._closing_ok = True

    def close_window(self):
        """Đóng không hỏi (đã lưu hoặc người dùng đã chọn)."""
        self._finish_close()
        self.close()

    def closeEvent(self, event):
        if not self._closing_ok:
            if not self.saved:
                answer = ask_yes_no_cancel(
                    self, "Bản dịch chưa lưu",
                    "Bản dịch này chưa được lưu.\n\n"
                    "Có = Lưu vào data.json rồi đóng\n"
                    "Không = Đóng (nháp vẫn giữ, mở lại bằng nút \"Mở nháp\")\n"
                    "Hủy = Quay lại")
                if answer is None:
                    event.ignore()
                    return
                if answer:
                    event.ignore()
                    QTimer.singleShot(0, self.save_data)   # lưu xong tự đóng
                    return
            self._finish_close()
        if self in self.app.reviews:
            self.app.reviews.remove(self)
        self.app.review_closed()
        super().closeEvent(event)

    # ── giao diện ──

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 6)
        bar = hbox(button("🔍 Kiểm tra lỗi", self.check_translation_errors),
                   button("🔄 Dịch lại toàn bộ", self.retranslate_all), "stretch",
                   button("✎ Thêm Name", self.prompt_add_name, "#6a5683"),
                   button("📚 Lưu vào thư viện", self.save_to_library, ACCENT),
                   button("💾 Lưu data.json", self.save_data, "#4f7f58"))
        root.addLayout(bar)
        root.addWidget(label("Bôi đen chữ rồi chuột phải để thêm Name  ·  Bấm đúp một dòng để sửa câu",
                             "#8a7f70", 9))
        self.text = PlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(f"QPlainTextEdit {{ background: {PANEL}; font-size: 11pt; padding: 8px; }}")
        self.text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text.customContextMenuRequested.connect(self.show_context_menu)
        self.text.viewport().installEventFilter(self)
        self._highlighter = _PairHighlighter(self.text.document())
        root.addWidget(self.text, 1)
        self.status_lbl = label("", "#8a7f70", 9)
        root.addWidget(self.status_lbl)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_data)
        self.find_bar = FindBar(self.text, self)
        root.insertWidget(2, self.find_bar)
        QShortcut(QKeySequence("Ctrl+F"), self, self.find_bar.open_bar)
        QShortcut(QKeySequence("F3"), self, lambda: self.find_bar.step(1))
        QShortcut(QKeySequence("Shift+F3"), self, lambda: self.find_bar.step(-1))

    def eventFilter(self, obj, event):
        if obj is self.text.viewport() and event.type() == QEvent.Type.MouseButtonDblClick:
            pair = self._pair_at(self.text.cursorForPosition(event.position().toPoint()))
            if pair is not None:
                self.edit_line(pair)
            return True
        return super().eventFilter(obj, event)

    def _pair_at(self, cursor):
        pair, offset = divmod(cursor.blockNumber(), 3)
        if offset in (0, 1) and 0 <= pair < len(self.vi_lines):
            return pair
        return None

    def _vi_block(self, index):
        return self.text.document().findBlockByNumber(index * 3 + 1)

    def load_content(self):
        bar = self.text.verticalScrollBar()
        scroll = bar.value()
        parts = []
        for cn, vi in zip(self.cn_lines, self.vi_lines):
            parts += (cn, vi, "")
        self.text.setPlainText("\n".join(parts))
        bar.setValue(scroll)

    def _replace_vi(self, index, new_text):
        block = self._vi_block(index)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(new_text)
        self.vi_lines[index] = new_text

    def show_context_menu(self, pos):
        pair = self._pair_at(self.text.cursorForPosition(pos))
        menu = QMenu(self)
        add = menu.addAction("Sửa lỗi & Thêm Name (từ đoạn bôi đen)", self.prompt_add_name)
        add.setEnabled(bool(selected_text(self.text).strip()))
        edit = menu.addAction("Sửa câu dịch của đoạn này", lambda: self.edit_line(pair))
        edit.setEnabled(pair is not None)
        menu.addSeparator()
        menu.addAction("Sao chép", self.text.copy).setEnabled(self.text.textCursor().hasSelection())
        menu.exec(self.text.viewport().mapToGlobal(pos))

    def retranslate_all(self):
        if ask_yes_no(self, "Xác nhận", "Bạn có chắc muốn dịch lại toàn bộ truyện không? "
                                        "(Sẽ tốn thời gian gọi API từ đầu)"):
            self.close_window()
            self.app.start_thread()

    def check_translation_errors(self):
        doc = self.text.document()
        selections = []
        first = None
        for i, line in enumerate(self.vi_lines):
            block = self._vi_block(i)
            pos = qt_offsets(line)
            for match in core.TRANSLATION_ERROR_RE.finditer(line):
                sel = QTextEdit.ExtraSelection()
                sel.cursor = QTextCursor(doc)
                sel.cursor.setPosition(block.position() + pos(match.start()))
                sel.cursor.setPosition(block.position() + pos(match.end()), QTextCursor.KeepAnchor)
                sel.format.setBackground(QColor("#9a3f35"))
                sel.format.setForeground(QColor("white"))
                selections.append(sel)
                if first is None:
                    first = QTextCursor(sel.cursor)
        self.text.setExtraSelections(selections)
        if selections:
            warn(self, "Phát hiện lỗi", f"Tìm thấy {len(selections)} chỗ chưa dịch, lỗi font () hoặc [Lỗi dịch].\n"
                                        "Đã bôi đỏ các chỗ này — bấm đúp dòng để sửa.")
            first.clearSelection()
            self.text.setTextCursor(first)
            self.text.ensureCursorVisible()
        else:
            info(self, "Hoàn tất", "Không phát hiện ký tự tiếng Trung chưa dịch hay lỗi font.")

    # ── sửa trực tiếp một câu ──

    def edit_line(self, index):
        if index is None or not 0 <= index < len(self.vi_lines):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Sửa đoạn {index + 1}/{len(self.vi_lines)}")
        restore_geometry(dlg, "builder_edit_line", 760, 360)
        lay = QVBoxLayout(dlg)
        lay.addWidget(label("Tiếng Trung gốc:"))
        cn_box = PlainTextEdit(self.cn_lines[index])
        cn_box.setReadOnly(True)
        cn_box.setMaximumHeight(90)
        cn_box.setStyleSheet(f"QPlainTextEdit {{ background: {BG}; color: {MUTED}; font-family: '{CN_FONT}'; font-size: 11pt; }}")
        lay.addWidget(cn_box)
        lay.addWidget(label("Bản dịch (Ctrl+Enter để lưu, Esc để hủy):", OK_GREEN, bold=True))
        vi_box = PlainTextEdit(self.vi_lines[index])
        vi_box.setStyleSheet(f"QPlainTextEdit {{ background: {FIELD}; font-size: 11pt; }}")
        lay.addWidget(vi_box, 1)
        vi_box.moveCursor(QTextCursor.End)
        vi_box.setFocus()

        def apply():
            # Mỗi đoạn phải nằm trên một dòng để giữ cặp Trung/Việt.
            new_text = unicodedata.normalize("NFC", " ".join(raw_text(vi_box).split()))
            if new_text != self.vi_lines[index]:
                self._replace_vi(index, new_text)
                self.mark_changed()
            dlg.accept()

        lay.addLayout(hbox("stretch", button("💾 Lưu câu", apply, "#4f7f58"), button("Hủy", dlg.reject)))
        QShortcut(QKeySequence("Ctrl+Return"), vi_box, apply, context=Qt.WidgetShortcut)
        dlg.finished.connect(lambda _r: save_geometry(dlg, "builder_edit_line"))
        dlg.exec()

    # ── thêm / sửa name ──

    def prompt_add_name(self):
        picked = selected_text(self.text).strip()
        is_cn = any("一" <= ch <= "鿿" for ch in picked)
        dlg = _GuardedDialog(self)
        dlg.setWindowTitle("Sửa lỗi & Thêm Name Mới")
        restore_geometry(dlg, "builder_add_name", 460, 360)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.addWidget(label("1. Tiếng Trung gốc (để lưu Name cho các lần dịch):"))
        ent_cn = LineEdit(picked if is_cn else "")
        lay.addWidget(ent_cn)
        lay.addWidget(label("2. Cụm từ VN bị dịch sai (để thay thế trong bài này):"))
        ent_wrong = LineEdit(picked if picked and not is_cn else "")
        lay.addWidget(ent_wrong)
        lay.addWidget(label("3. Sửa thành (Name đúng):", OK_GREEN, bold=True))
        ent_right = LineEdit()
        lay.addWidget(ent_right)
        temp_box = QCheckBox("🏷 Name tạm — chỉ dùng cho lượt dịch này, không lưu name.cfg")
        temp_box.setStyleSheet("color: #e8c27a;")
        lay.addWidget(temp_box)
        btn_quick = button("🚀 Cập nhật nhanh (Enter)", lambda: apply_name(False), ACCENT)
        btn_retrans = button("🔄 Dịch Lại Toàn Bộ", lambda: apply_name(True), "#8a5a22")
        lay.addStretch(1)
        lay.addLayout(hbox("stretch", btn_quick, btn_retrans, "stretch"))
        ent_right.setFocus()
        busy = dlg.state

        if is_cn and picked:
            # Gợi ý Name bằng API dịch; điền ô qua luồng giao diện.
            def fetch_suggestion(cn_text):
                res = self.app.translate_api(cn_text)
                suggestion = res.strip().title() if res else ""
                if suggestion:
                    self.app.bridge.call(lambda: ent_right.text() or ent_right.setText(suggestion))
            threading.Thread(target=fetch_suggestion, args=(picked,), daemon=True).start()

        def set_busy(on):
            busy["on"] = on
            for widget in (ent_cn, ent_wrong, ent_right, btn_quick, btn_retrans, temp_box):
                widget.setEnabled(not on)
            dlg.setWindowTitle("Đang cập nhật Name..." if on else "Sửa lỗi & Thêm Name Mới")

        def apply_name(retranslate=False):
            if busy["on"]:
                return
            cn_val = unicodedata.normalize("NFC", ent_cn.text().strip())
            wrong_val = unicodedata.normalize("NFC", ent_wrong.text().strip())
            right_val = unicodedata.normalize("NFC", ent_right.text().strip())
            if not right_val:
                warn(dlg, "Chú ý", "Vui lòng nhập 'Name đúng'!")
                return
            if retranslate:
                if not cn_val:
                    warn(dlg, "Chú ý", "Để dịch lại từ đầu, bắt buộc phải có 'Tiếng Trung gốc'!")
                    return
                if not self.app.add_names([(cn_val, right_val)], temp_box.isChecked(), parent=dlg):
                    return
                dlg.accept()
                self.close_window()
                self.app.start_thread()
                return
            if not wrong_val and not cn_val:
                warn(dlg, "Chú ý", "Vui lòng nhập ít nhất 'Tiếng Trung' hoặc 'Từ sai'!")
                return
            set_busy(True)
            vi_names = list(self.app.effective_names().values()) + [right_val]
            temporary = temp_box.isChecked()
            snapshot = tuple(self.vi_lines)

            def compute():
                try:
                    wrong = wrong_val
                    if not wrong and cn_val:
                        auto_vi = self.app.translate_api(cn_val)
                        if auto_vi:
                            wrong = unicodedata.normalize("NFC", auto_vi.strip())
                    updates = core.prepare_name_updates(snapshot, wrong, right_val, vi_names)
                    self.app.bridge.call(finish, wrong, updates, None)
                except Exception as exc:
                    self.app.bridge.call(finish, "", [], str(exc))

            def finish(wrong, updates, err):
                if err:
                    set_busy(False)
                    error(dlg, "Lỗi cập nhật Name", err)
                    return
                if not wrong and not ask_yes_no(dlg, "Xác nhận", "Không tìm được cụm từ VN cần thay. "
                                                                 "Chỉ lưu Name để áp dụng khi dịch lại?"):
                    set_busy(False)
                    return
                for index, translated in updates:
                    self._replace_vi(index, translated)
                if cn_val:
                    self.app.add_names([(cn_val, right_val)], temporary, parent=self)
                busy["on"] = False
                dlg.accept()
                if updates:
                    self.mark_changed()
                where = " · name tạm" if temporary else " · đã lưu vào name.cfg"
                self.set_status(f"✅ {cn_val or wrong_val} → {right_val}: đã sửa {len(updates)} đoạn"
                                + (where if cn_val else ""))

            threading.Thread(target=compute, daemon=True).start()

        for entry in (ent_cn, ent_wrong, ent_right):
            entry.returnPressed.connect(lambda: apply_name(False))
        dlg.finished.connect(lambda _r: save_geometry(dlg, "builder_add_name"))
        dlg.exec()

    # ── lưu ──

    def save_data(self):
        output_dir = os.path.join(STORIES_DIR, self.slug)
        data_path = os.path.join(output_dir, "data.json")
        if os.path.exists(data_path) and not self._saved_data_once:
            if not ask_yes_no(self, "Ghi đè truyện?",
                              f"stories/{self.slug}/data.json đã tồn tại (có thể là truyện khác trùng tên).\n\nGhi đè?",
                              default_no=True, warning=True):
                return
        try:
            os.makedirs(output_dir, exist_ok=True)
            store.write_json_atomic(data_path, core.story_data(self.title, self.cn_lines, self.vi_lines))
            core.update_story_catalog(self.title, self.slug)
        except Exception as exc:
            error(self, "Lỗi khi lưu", str(exc))
            return
        self._saved_data_once = True
        self.saved = True
        cleared = self.app.clear_temp_names()
        self.app.set_status("✅ Đã lưu data.json thành công!" + (f" · đã xoá {cleared} name tạm" if cleared else ""),
                            OK_GREEN)
        info(self, "Thành công", f"Đã xuất dữ liệu truyện: {self.slug}")
        self.close_window()

    def save_to_library(self):
        try:
            catalog = read_catalog(LIBRARY_CATALOG)
        except CatalogError as exc:
            error(self, "Không đọc được danh mục thư viện", f"{exc}\n\nĐã dừng để không ghi đè list.json.")
            return
        result = LibraryDialog(self, catalog).exec_plan()
        if not result:
            return
        slug, title, chapters = result
        self.saved = True
        first, last = chapters[0][0], chapters[-1][0]
        span = first if first == last else f"{first}–{last}"
        self.set_status(f"📚 Đã lưu {len(chapters)} chương vào library/{slug} ({span}) · {title}")
        cleared = self.app.clear_temp_names()
        self.app.set_status(f"📚 Đã lưu vào thư viện: {slug} | {title}"
                            + (f" · đã xoá {cleared} name tạm" if cleared else ""), OK_GREEN)


class _GuardedDialog(QDialog):
    """Hộp thoại không đóng được (Esc, nút X) khi state["on"] — đang cập nhật giữa chừng."""

    def __init__(self, parent):
        super().__init__(parent)
        self.state = {"on": False}

    def reject(self):
        if not self.state["on"]:
            super().reject()

    def closeEvent(self, event):
        if self.state["on"]:
            event.ignore()
        else:
            super().closeEvent(event)


def chapter_name_key(name):
    """So tên chương không phân biệt dấu, hoa thường, khoảng trắng."""
    return re.sub(r"\s+", " ", search_key(name or "")).strip()


class LibraryDialog(QDialog):
    """📚 Lưu vào thư viện: chọn truyện, cách chia chương, chương cần lưu."""

    def __init__(self, review, catalog):
        super().__init__(review)
        self.review = review
        self.catalog = catalog
        self.result_plan = None
        self.setWindowTitle("📚 Lưu vào thư viện")
        restore_geometry(self, "builder_library_dialog", 700, 700)
        self.setMinimumSize(560, 560)
        self.options = [f'{item["slug"]} | {item.get("title", "")}' for item in
                        sorted(catalog, key=lambda it: float(it.get("timestamp") or 0), reverse=True)
                        if item.get("slug")]
        self.pairs = list(zip(review.cn_lines, review.vi_lines))
        self.patterns = list(store.DEFAULT_SPLIT_PATTERNS)
        for item in core.load_config().get("split_patterns", []):
            if isinstance(item, (list, tuple)) and len(item) == 2 and not any(item[1] == rx for _n, rx in self.patterns):
                self.patterns.append((item[0], item[1]))
        self.plan = {"slug": None, "title": None, "chapters": [], "error": None}
        self.state = {"key": None, "groups": [], "picked": [], "existing": set(), "start": 1, "is_new": True}
        self._build()
        self.refresh_story_list()
        self.story_filter.setFocus()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        head = dict(color=MUTED, size=9, bold=True)
        # 1. Truyện
        lay.addWidget(label("1. TRUYỆN", **head))
        self.r_new, self.r_exist = QRadioButton("Truyện mới:"), QRadioButton("Truyện có sẵn — tìm:")
        group = QButtonGroup(self)
        group.addButton(self.r_new)
        group.addButton(self.r_exist)
        (self.r_exist if self.options else self.r_new).setChecked(True)
        self.new_title = LineEdit(self.review.title)
        self.story_filter = LineEdit()
        lay.addLayout(hbox(self.r_new, (self.new_title, 1)))
        lay.addLayout(hbox(self.r_exist, (self.story_filter, 1)))
        self.story_list = QListWidget()
        self.story_list.setMaximumHeight(130)
        lay.addWidget(self.story_list)
        # 2. Chương
        lay.addWidget(label("2. CHIA CHƯƠNG", **head))
        self.r_one, self.r_split = QRadioButton("Một chương, tên:"), QRadioButton("Tách theo mẫu:")
        group2 = QButtonGroup(self)
        group2.addButton(self.r_one)
        group2.addButton(self.r_split)
        self.r_one.setChecked(True)
        self.one_title = LineEdit(self.review.title)
        self.pattern = QComboBox()
        self.pattern.setEditable(True)
        self.pattern.addItems([rx for _n, rx in self.patterns])
        self.pattern.setStyleSheet("font-family: Consolas; font-size: 9pt;")
        lay.addLayout(hbox(self.r_one, (self.one_title, 1)))
        lay.addLayout(hbox(self.r_split, (self.pattern, 1)))
        lay.addWidget(label(" · ".join(n for n, _ in self.patterns), HINT, 9, wrap=True))
        # 3. Chọn chương
        lay.addWidget(label("3. CHỌN CHƯƠNG ĐỂ LƯU", **head))
        self.range_entry = LineEdit()
        self.range_entry.setFixedWidth(140)
        lay.addLayout(hbox(self.range_entry, button("Chọn khoảng", self.pick_range, small=True),
                           button("Tất cả", lambda: self.pick_all(True), small=True),
                           button("Bỏ hết", lambda: self.pick_all(False), small=True),
                           button("Bỏ chương đã có", self.pick_missing, small=True), "stretch"))
        lay.addWidget(label("Bấm vào dòng hoặc phím Space để tick/bỏ · Khoảng: 41-60 hoặc 1-5, 8 (theo cột #)", HINT, 9))
        self.tree = _KeyTree({Qt.Key_Space: lambda: self.toggle(self.selected_rows())})
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["✓", "#", "Mã", "Tên chương", "Đoạn"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for col, width in enumerate((34, 46, 60, 300, 60)):
            self.tree.setColumnWidth(col, width)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tree.itemClicked.connect(lambda item, _col: self.toggle([int(item.data(0, Qt.UserRole))]))
        lay.addWidget(self.tree, 1)
        self.summary = label("", MUTED, 9, wrap=True)
        lay.addWidget(self.summary)
        self.save_btn = button("📚 Lưu vào thư viện", self.do_save, ACCENT, bold=True)
        lay.addLayout(hbox("stretch", self.save_btn, button("Hủy", self.reject)))

        self.story_filter.textEdited.connect(lambda _t: (self.r_exist.setChecked(True), self.refresh_story_list()))
        self.story_list.currentRowChanged.connect(lambda _r: self.update_preview())
        self.story_list.itemClicked.connect(lambda _i: (self.r_exist.setChecked(True), self.update_preview()))
        self.new_title.textEdited.connect(lambda _t: (self.r_new.setChecked(True), self.update_preview()))
        self.one_title.textEdited.connect(lambda _t: (self.r_one.setChecked(True), self.update_preview()))
        self.pattern.currentTextChanged.connect(lambda _t: (self.r_split.setChecked(True), self.update_preview()))
        for radio in (self.r_new, self.r_exist, self.r_one, self.r_split):
            radio.toggled.connect(lambda on: on and self.update_preview())
        self.range_entry.returnPressed.connect(self.pick_range)

    def exec_plan(self):
        """Mở hộp thoại; trả (slug, title, chapters) khi đã lưu, ngược lại None."""
        self.exec()
        return self.result_plan

    def done(self, code):
        save_geometry(self, "builder_library_dialog")
        super().done(code)

    def refresh_story_list(self):
        words = search_key(self.story_filter.text()).split()
        current = self.story_list.currentItem().text() if self.story_list.currentItem() else None
        self.story_list.blockSignals(True)
        self.story_list.clear()
        items = [o for o in self.options if all(w in search_key(o) for w in words)]
        self.story_list.addItems(items)
        if current in items:
            self.story_list.setCurrentRow(items.index(current))
        elif items:
            self.story_list.setCurrentRow(0)
        self.story_list.blockSignals(False)
        self.update_preview()

    def selected_story(self):
        if self.r_new.isChecked():
            title = self.new_title.text().strip()
            return (store.next_story_id(self.catalog), title, True) if title else (None, None, True)
        item = self.story_list.currentItem()
        if item:
            slug, title = (p.strip() for p in item.text().split("|", 1))
            return slug, title, False
        return None, None, False

    def update_preview(self):
        """Chia lại chương khi đổi truyện/mẫu; giữ lựa chọn nếu cách chia không đổi."""
        slug, title, is_new = self.selected_story()
        plan, state = self.plan, self.state
        plan.update(slug=slug, title=title, error=None)
        groups = []
        if not slug:
            plan["error"] = "Chọn truyện có sẵn hoặc nhập tên truyện mới."
        elif self.r_one.isChecked():
            groups = [(self.one_title.text().strip() or "Oneshot", self.pairs)]
        else:
            try:
                found = store.split_into_chapters(self.pairs, self.pattern.currentText().strip() or "^$",
                                                  text_of=lambda p: p[1])
                groups = [(g["title"], g["items"]) for g in found if g["items"]]
            except re.error as exc:
                plan["error"] = f"Regex lỗi: {exc}"
        story = next((s for s in self.catalog if s.get("slug") == slug), None) if slug and not is_new else None
        existing = {chapter_name_key(c.get("name")) for c in (story or {}).get("chapters", [])} - {""}
        key = (slug, self.r_one.isChecked(), tuple(n for n, _ in groups), tuple(len(i) for _, i in groups))
        if key != state["key"]:
            # Đổi truyện đích hoặc cách chia: tick sẵn những chương chưa có trong truyện.
            picked = [chapter_name_key(n) not in existing for n, _ in groups]
            if groups and not any(picked):
                picked = [True] * len(groups)
            state.update(key=key, picked=picked)
        state.update(groups=groups, existing=existing, is_new=is_new,
                     start=int(store.next_chapter_id(self.catalog, slug)) if slug else 1)
        self.draw()

    def draw(self):
        """Vẽ bảng + lập kế hoạch lưu: chỉ chương được tick, mã nối tiếp truyện."""
        plan, state = self.plan, self.state
        groups, picked = state["groups"], state["picked"]
        plan["chapters"] = []
        next_no = state["start"]
        scroll = self.tree.verticalScrollBar().value()
        self.tree.clear()
        off, dup_color = QColor(HINT), QColor("#c9a063")
        rows = []
        for i, (name, items) in enumerate(groups):
            name = name or f"Chương {i + 1}"
            dup = chapter_name_key(name) in state["existing"]
            chap_id = ""
            if picked[i]:
                chap_id = store.format_chapter_id(next_no)
                plan["chapters"].append((chap_id, name, items))
                next_no += 1
            item = QTreeWidgetItem(["☑" if picked[i] else "☐", str(i + 1), chap_id,
                                    name[:120] + ("  · đã có" if dup else ""), str(len(items))])
            item.setData(0, Qt.UserRole, i)
            for col, align in ((0, Qt.AlignCenter), (1, Qt.AlignRight), (2, Qt.AlignCenter), (4, Qt.AlignRight)):
                item.setTextAlignment(col, align | Qt.AlignVCenter)
            if dup or not picked[i]:
                for col in range(5):
                    item.setForeground(col, dup_color if dup else off)
            rows.append(item)
        self.tree.addTopLevelItems(rows)
        self.tree.verticalScrollBar().setValue(scroll)
        if plan["error"]:
            set_label(self.summary, plan["error"], ERROR)
        else:
            n = len(plan["chapters"])
            span = ""
            if n:
                first, last = plan["chapters"][0][0], plan["chapters"][-1][0]
                span = f" → mã {first}" + (f"–{last}" if first != last else "")
            head = "TRUYỆN MỚI" if state["is_new"] else "Truyện"
            dups = sum(1 for name, _ in groups if chapter_name_key(name) in state["existing"])
            set_label(self.summary, f"{head} {plan['slug']} | {plan['title']} — lưu {n}/{len(groups)} chương{span}"
                      + (f" · {dups} chương trùng tên với chương đã có" if dups else ""), MUTED)
        self.save_btn.setEnabled(bool(plan["chapters"]) and not plan["error"])
        self.save_btn.setText(f"📚 Lưu {len(plan['chapters'])} chương vào thư viện" if plan["chapters"]
                              else "📚 Lưu vào thư viện")

    def selected_rows(self):
        return [int(item.data(0, Qt.UserRole)) for item in self.tree.selectedItems()]

    def toggle(self, indexes):
        if not indexes:
            return
        value = not all(self.state["picked"][i] for i in indexes)
        for i in indexes:
            self.state["picked"][i] = value
        self.draw()
        for i in indexes:
            self.tree.topLevelItem(i).setSelected(True)
        self.tree.setCurrentItem(self.tree.topLevelItem(indexes[-1]), 0, QItemSelectionModel.NoUpdate)

    def pick_all(self, value):
        self.state["picked"] = [value] * len(self.state["groups"])
        self.draw()

    def pick_missing(self):
        self.state["picked"] = [chapter_name_key(n) not in self.state["existing"] for n, _ in self.state["groups"]]
        self.draw()

    def pick_range(self):
        try:
            chosen = core.parse_ranges(self.range_entry.text())
        except ValueError as exc:
            warn(self, "Khoảng không hợp lệ", f"Không hiểu “{exc}”. Ví dụ: 41-60 hoặc 1-5, 8")
            return
        if chosen:
            self.state["picked"] = [(i + 1) in chosen for i in range(len(self.state["groups"]))]
            self.draw()

    def do_save(self):
        plan = self.plan
        if not plan["chapters"]:
            return
        # Truyện mới: để save_chapters tự cấp mã từ catalog đọc mới nhất,
        # tránh dùng mã đã xem trước khi có người khác thêm truyện.
        slug = None if self.r_new.isChecked() else plan["slug"]
        try:
            _catalog, slug, _saved = store.save_chapters(
                LIBRARY_DIR, BASE_DIR, LIBRARY_CATALOG, slug, plan["title"], plan["chapters"])
        except store.ChapterClashError as exc:
            error(self, "Trùng mã chương", f"Chương {', '.join(exc.chapter_ids[:5])} đã tồn tại. "
                                           "Mở lại hộp thoại để lấy mã mới.")
            return
        except CatalogError as exc:
            error(self, "Không đọc được danh mục", str(exc))
            return
        except Exception as exc:
            error(self, "Lỗi khi lưu thư viện", str(exc))
            return
        self.result_plan = (slug, plan["title"], list(plan["chapters"]))
        self.accept()


class _KeyTree(QTreeWidget):
    """QTreeWidget với phím tắt riêng ({Qt.Key: hàm}); phím khác giữ hành vi mặc định."""

    def __init__(self, keys=None):
        super().__init__()
        self.keys = keys or {}
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)

    def keyPressEvent(self, event):
        handler = self.keys.get(event.key())
        if handler is not None and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier):
            handler()
            return
        super().keyPressEvent(event)


# ═════════════════════════ Scan Names ═════════════════════════

class ScanNamesDialog(QDialog):
    COLUMNS = (("sel", "✓", 34), ("cn", "Tiếng Trung", 130), ("type", "Loại", 80), ("count", "Xuất hiện", 80),
               ("conf", "Điểm", 64), ("vi", "Bản dịch sẽ lưu", 220), ("alt", "Gợi ý còn lại", 180))
    SOURCES = (("moxhi_vi", "Moxhi"), ("hanviet", "HV"), ("api_vi", "API"))

    def __init__(self, app, candidates):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("🔍 Scan Names — Danh sách tên phát hiện")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        restore_geometry(self, "builder_scan_names", 920, 680)
        self.setMinimumSize(760, 560)
        self.candidates = candidates
        self.by_cn = {c["cn"]: c for c in candidates}
        self.ignored = set()
        self.edited = {c["cn"]: c.get("suggested_vi", "") for c in candidates}
        self.selected = set()
        self.sort = {"col": None, "reverse": False}
        self.current = None
        self.tier = "sure" if any(core.is_sure_candidate(c) for c in candidates) else "review"
        self.source_text = raw_text(app.txt_area)
        self._filter_timer = QTimer(self, singleShot=True, interval=150)
        self._filter_timer.timeout.connect(self.rebuild)
        self._build()
        self.rebuild()
        self.tree.setFocus()

    # ── dựng giao diện ──

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(0)
        top = QFrame()
        top.setStyleSheet(f"QFrame {{ background: {PANEL}; }} QWidget {{ background: {PANEL}; }}")
        tl = QVBoxLayout(top)
        tl.setContentsMargins(16, 10, 16, 6)
        self.count_lbl = label(f"{len(self.candidates)} ứng viên tìm được", MUTED, 9)
        tl.addLayout(hbox(label("🔍 Scan Names", "#f4ede1", 12, True), self.count_lbl, "stretch",
                          button("🔄 Quét lại", self.rerun, "#3a332c", small=True)))
        self.tier_buttons = {}
        tiers = []
        for key, text in (("sure", "Chắc chắn"), ("review", "Cần xem"), ("all", "Tất cả")):
            btn = button(text, lambda k=key: self.set_tier(k))
            self.tier_buttons[key] = (btn, text)
            tiers.append(btn)
        tl.addLayout(hbox(*tiers, "stretch", label("Chắc chắn = 2 bộ quét cùng thấy, tên ≥2 chữ điểm ≥95%, "
                                                    "hoặc lặp lại nhiều lần · Cần xem: còn lại", HINT, 9)))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["TẤT CẢ"] + sorted({c["type"] for c in self.candidates}))
        self.min_conf = QSpinBox()
        self.min_conf.setRange(0, 99)
        self.search = LineEdit()
        self.search.setFixedWidth(170)
        tl.addLayout(hbox(label("Lọc:", MUTED, 9), self.type_combo, label("Điểm ≥", MUTED, 9), self.min_conf,
                          label("%", MUTED, 9), label("  Tìm:", MUTED, 9), self.search, "stretch",
                          label("Space: chọn · Del: bỏ qua · Enter: sửa · F2: đổi Moxhi/Hán-Việt/API", HINT, 9)))
        lay.addWidget(top)
        if not self.candidates:
            lay.addWidget(label("Bộ quét không tìm thấy tên mới. Có thể thêm thủ công ở phía dưới.", WARN))

        self.tree = _KeyTree({Qt.Key_Space: lambda: self.toggle(self.selection()),
                              Qt.Key_Delete: lambda: self.ignore_rows(self.selection()),
                              Qt.Key_F2: self.swap_sources,
                              Qt.Key_Return: self.focus_vi, Qt.Key_Enter: self.focus_vi})
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels([c[1] for c in self.COLUMNS])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for i, (_key, _text, width) in enumerate(self.COLUMNS):
            self.tree.setColumnWidth(i, width)
        self.tree.header().setSectionsClickable(True)
        self.tree.header().sectionClicked.connect(lambda i: self.sort_by(self.COLUMNS[i][0]))
        self.tree.currentItemChanged.connect(lambda cur, _prev: self.show_detail(cur.data(0, Qt.UserRole) if cur else None))
        self.tree.itemClicked.connect(lambda item, col: col == 0 and self.toggle([item.data(0, Qt.UserRole)]))
        self.tree.itemDoubleClicked.connect(lambda _item, _col: self.focus_vi())
        table = QVBoxLayout()
        table.setContentsMargins(12, 6, 12, 0)
        table.addWidget(self.tree)
        lay.addLayout(table, 1)

        detail = QFrame()
        detail.setStyleSheet(f"QFrame {{ background: {PANEL}; }} QLabel {{ background: {PANEL}; }}")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(12, 8, 12, 8)
        self.detail_cn = label("—", "#f4ede1", 14, True)
        self.detail_cn.setFont(QFont(CN_FONT, 14, QFont.Bold))
        self.detail_meta = label("", MUTED, 9)
        dl.addLayout(hbox(self.detail_cn, (self.detail_meta, 1)))
        self.vi_entry = _ScanEntry(self)
        self.vi_entry.setStyleSheet(f"background: {FIELD}; font-size: 11pt;")
        self.vi_entry.textEdited.connect(self.on_vi_change)
        dl.addLayout(hbox(label("Bản dịch:", OK_GREEN, 9, True), (self.vi_entry, 1),
                          button("Copy Hán", self.copy_chinese, ACCENT, small=True, bold=True),
                          button("Thêm", self.add_current, "#46734f", small=True, bold=True),
                          button("Bỏ qua", lambda: self.ignore_rows(self.selection()), "#3a332c", small=True, bold=True)))
        self.moxhi_btn = button("Moxhi: —", lambda: self.use_source("moxhi_vi"), FIELD, fg="#c9b8e0", small=True)
        self.hv_btn = button("Hán-Việt: —", lambda: self.use_source("hanviet"), FIELD, fg="#f0d9a8", small=True)
        self.api_btn = button("API: —", lambda: self.use_source("api_vi"), FIELD, fg="#ddd5c7", small=True)
        dl.addLayout(hbox(label("Gợi ý:", MUTED, 9), self.moxhi_btn, self.hv_btn, self.api_btn, "stretch"))
        self.context = QTextEdit()
        self.context.setReadOnly(True)
        self.context.setFixedHeight(92)
        self.context.setStyleSheet(f"QTextEdit {{ background: {BG}; color: {MUTED}; font-family: '{CN_FONT}'; font-size: 10pt; }}")
        self.context.viewport().installEventFilter(self)
        dl.addWidget(self.context)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(12, 6, 12, 0)
        wrap.addWidget(detail)
        lay.addLayout(wrap)
        self.status = label("", OK_GREEN, 9)
        lay.addLayout(hbox(self.status, margins=(16, 4, 16, 0)))

        # Thêm tên thủ công: cho tên bộ quét bỏ sót (bôi đen trong ngữ cảnh để điền nhanh)
        manual = QFrame()
        manual.setStyleSheet(f"QFrame {{ background: {PANEL}; }} QLabel {{ background: {PANEL}; }}")
        ml = QHBoxLayout(manual)
        ml.setContentsMargins(12, 8, 12, 8)
        self.manual_cn = LineEdit()
        self.manual_cn.setFixedWidth(140)
        self.manual_cn.setFont(QFont(CN_FONT, 11))
        self.manual_vi = LineEdit()
        self.manual_info = label("", MUTED, 9)
        self.manual_info.setMinimumWidth(150)
        self.manual_auto = ""
        for w in (label("Thêm tên thủ công:", WARN, 9, True), self.manual_cn, label("="), self.manual_vi):
            ml.addWidget(w, 1 if w is self.manual_vi else 0)
        ml.addWidget(self.manual_info)
        ml.addWidget(button("Thêm", self.add_manual, "#46734f", small=True, bold=True))
        wrap2 = QVBoxLayout()
        wrap2.setContentsMargins(12, 4, 12, 0)
        wrap2.addWidget(manual)
        lay.addLayout(wrap2)
        lay.addLayout(hbox(label("Mẹo: bôi đen một tên trong khung ngữ cảnh ở trên để điền nhanh vào ô thêm thủ công.",
                                 HINT, 9), margins=(16, 2, 16, 4)))
        self.temp_box = QCheckBox("🏷 Thêm làm name tạm")
        self.temp_box.setStyleSheet("color: #e8c27a;")
        lay.addLayout(hbox(button("Chọn mục đang hiện (có bản dịch)", lambda: self.select_visible(True), fg="#ddd5c7"),
                           button("Bỏ chọn đang hiện", lambda: self.select_visible(False), fg=MUTED), "stretch",
                           self.temp_box, button("✅ Thêm các mục đã chọn", self.add_selected, "#6a5683", bold=True),
                           button("Đóng", self.reject, fg=MUTED), margins=(12, 8, 12, 0)))

        self.type_combo.currentTextChanged.connect(lambda _t: self.rebuild())
        self.min_conf.valueChanged.connect(lambda _v: self._filter_timer.start())
        self.search.textChanged.connect(lambda _t: self._filter_timer.start())
        self.manual_cn.textChanged.connect(self.on_manual_cn)
        self.manual_cn.returnPressed.connect(self.manual_vi.setFocus)
        self.manual_vi.returnPressed.connect(self.add_manual)

    def eventFilter(self, obj, event):
        if obj is self.context.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            QTimer.singleShot(0, self.take_selection)
        return super().eventFilter(obj, event)

    def done(self, code):
        self._filter_timer.stop()
        save_geometry(self, "builder_scan_names")
        super().done(code)

    def rerun(self):
        self.reject()
        self.app.open_scan_names_dialog()

    # ── bảng ──

    def alternative(self, c):
        """Gợi ý không đang dùng (Moxhi, Hán-Việt hoặc API) để so nhanh."""
        current_value = self.edited[c["cn"]].strip()
        for key, name in self.SOURCES:
            value = (c.get(key) or "").strip()
            if value and value != current_value:
                return f"{name}: {value}"
        return ""

    def row_values(self, c):
        cn = c["cn"]
        return ["☑" if cn in self.selected else "☐", cn, c["type"], str(c["count"]),
                f"{int(c['confidence'] * 100)}%", self.edited[cn], self.alternative(c)]

    def _paint_item(self, item, c):
        for col, value in enumerate(self.row_values(c)):
            item.setText(col, value)
        color = None
        if not self.edited[c["cn"]].strip():
            color = QColor(WARN)
        elif c["cn"] in self.selected:
            color = QColor("#c9b8e0")
        for col in range(len(self.COLUMNS)):
            item.setForeground(col, color if color else QColor(TEXT))

    def matching(self):
        filter_type = self.type_combo.currentText()
        query = self.search.text().strip().casefold()
        min_conf = self.min_conf.value()
        rows = [c for c in self.candidates
                if c["cn"] not in self.ignored
                and (self.tier == "all" or core.is_sure_candidate(c) == (self.tier == "sure"))
                and (filter_type == "TẤT CẢ" or c["type"] == filter_type)
                and c["confidence"] * 100 >= min_conf
                and (not query or query in c["cn"].casefold() or query in self.edited[c["cn"]].casefold())]
        col = self.sort["col"]
        if col:
            keys = {"sel": lambda c: c["cn"] in self.selected, "cn": lambda c: c["cn"], "type": lambda c: c["type"],
                    "count": lambda c: c["count"], "conf": lambda c: c["confidence"],
                    "vi": lambda c: self.edited[c["cn"]].casefold(), "alt": self.alternative}
            rows.sort(key=keys[col], reverse=self.sort["reverse"])
        else:
            rows.sort(key=core.candidate_rank, reverse=True)
        return rows

    def rebuild(self):
        self._filter_timer.stop()
        focus = self.current
        self.tree.blockSignals(True)
        self.tree.clear()
        self.items = {}
        rows = self.matching()
        for c in rows:
            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, c["cn"])
            for col in (0, 2, 3, 4):
                item.setTextAlignment(col, Qt.AlignCenter)
            item.setFont(1, QFont(CN_FONT, 10))
            self._paint_item(item, c)
            self.items[c["cn"]] = item
        self.tree.addTopLevelItems(list(self.items.values()))
        self.tree.blockSignals(False)
        self.update_counts()
        target = focus if focus in self.items else (rows[0]["cn"] if rows else None)
        if target:
            self.focus_row(target)
        else:
            self.show_detail(None)

    def update_counts(self):
        left = [c for c in self.candidates if c["cn"] not in self.ignored]
        counts = {"sure": sum(1 for c in left if core.is_sure_candidate(c)), "all": len(left)}
        counts["review"] = counts["all"] - counts["sure"]
        for key, (btn, text) in self.tier_buttons.items():
            active = self.tier == key
            btn.setText(f"{text} ({counts[key]})")
            btn.setStyleSheet(f"QPushButton {{ background: {'#6a5683' if active else FIELD}; "
                              f"color: {'white' if active else MUTED}; }}")
        self.count_lbl.setText(f"{len(left)} ứng viên · đang hiện {self.tree.topLevelItemCount()} · "
                               f"đã chọn {len(self.selected)}")

    def refresh_row(self, cn, counts=True):
        item = self.items.get(cn)
        if item is not None and cn in self.by_cn:
            self._paint_item(item, self.by_cn[cn])
        if counts:
            self.update_counts()

    def set_tier(self, key):
        self.tier = key
        self.rebuild()

    def sort_by(self, col):
        if self.sort["col"] == col:
            self.sort["reverse"] = not self.sort["reverse"]
        else:
            self.sort.update(col=col, reverse=col in ("count", "conf", "sel"))
        self.tree.setHeaderLabels([text + ((" ▼" if self.sort["reverse"] else " ▲") if key == col else "")
                                   for key, text, _w in self.COLUMNS])
        self.rebuild()

    def selection(self):
        return [item.data(0, Qt.UserRole) for item in self.tree.selectedItems()]

    def focus_row(self, cn):
        item = self.items.get(cn)
        if item is None:
            return
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)
        self.show_detail(cn)

    # ── chi tiết ──

    def show_detail(self, cn):
        self.current = cn
        self.context.clear()
        if cn is None or cn not in self.by_cn:
            self.current = None
            self.detail_cn.setText("—")
            self.detail_meta.setText("")
            self.vi_entry.setText("")
            for btn, text in ((self.hv_btn, "Hán-Việt: —"), (self.api_btn, "API: —"), (self.moxhi_btn, "Moxhi: —")):
                btn.setText(text)
                btn.setEnabled(False)
            return
        c = self.by_cn[cn]
        self.detail_cn.setText(cn)
        signals = ", ".join(c.get("signals", []))
        self.detail_meta.setText(f"{c['type']} · {c['count']} lần · điểm {int(c['confidence'] * 100)}%"
                                 + (f" · căn cứ: {signals}" if signals else ""))
        self.vi_entry.setText(self.edited[cn])
        self.hv_btn.setText(f"Hán-Việt: {c.get('hanviet') or '— (chưa đủ âm)'}")
        self.hv_btn.setEnabled(bool(c.get("hanviet")))
        self.api_btn.setText(f"API: {c.get('api_vi') or '—'}")
        self.api_btn.setEnabled(bool(c.get("api_vi")))
        self.moxhi_btn.setText(f"Moxhi: {c.get('moxhi_vi') or '—'}")
        self.moxhi_btn.setEnabled(bool(c.get("moxhi_vi")))
        cursor = self.context.textCursor()
        plain, hit = QTextCharFormat(), QTextCharFormat()
        hit.setForeground(QColor("#f0d9a8"))
        hit.setBackground(QColor("#3a2a12"))
        for ctx in c.get("contexts", []) or ["(không có ngữ cảnh mẫu)"]:
            line = "… " + ctx.replace("\n", " ") + " …"
            for piece_i, piece in enumerate(line.split(cn)):
                if piece_i:
                    cursor.insertText(cn, hit)
                cursor.insertText(piece, plain)
            cursor.insertText("\n", plain)
        self.context.moveCursor(QTextCursor.Start)

    def on_vi_change(self, text):
        cn = self.current
        if cn is not None and self.edited.get(cn) != text:
            self.edited[cn] = text
            self.refresh_row(cn)

    def use_source(self, key, cns=None):
        cns = [cn for cn in (cns or [self.current]) if cn in self.by_cn]
        for cn in cns:
            value = (self.by_cn[cn].get(key) or "").strip()
            if value:
                self.edited[cn] = value
                self.refresh_row(cn)
        if self.current in cns:
            self.vi_entry.setText(self.edited[self.current])

    def swap_sources(self):
        """F2: xoay vòng sang gợi ý khác (Moxhi → Hán-Việt → API), bỏ qua gợi ý trống/trùng."""
        for cn in [cn for cn in (self.selection() or [self.current]) if cn in self.by_cn]:
            c = self.by_cn[cn]
            options = []
            for key, _ in self.SOURCES:
                value = (c.get(key) or "").strip()
                if value and value not in [v for _, v in options]:
                    options.append((key, value))
            if not options:
                continue
            values = [v for _, v in options]
            now = self.edited[cn].strip()
            nxt = options[(values.index(now) + 1) % len(options)] if now in values else options[0]
            self.use_source(nxt[0], [cn])

    def toggle(self, cns):
        cns = [cn for cn in cns if cn in self.by_cn]
        if not cns:
            return
        turn_on = any(cn not in self.selected for cn in cns)
        for cn in cns:
            (self.selected.add if turn_on else self.selected.discard)(cn)
            self.refresh_row(cn)

    def remove_rows(self, cns):
        order = [self.tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(self.tree.topLevelItemCount())]
        positions = [order.index(cn) for cn in cns if cn in order]
        following = None
        if positions:
            after = [cn for cn in order[max(positions) + 1:] if cn not in cns]
            before = [cn for cn in order[:min(positions)] if cn not in cns]
            following = (after or before or [None])[0]
        for cn in cns:
            self.selected.discard(cn)
            self.ignored.add(cn)
            item = self.items.pop(cn, None)
            if item is not None:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        if following:
            self.focus_row(following)
        else:
            self.show_detail(None)
        self.update_counts()

    def ignore_rows(self, cns):
        cns = [cn for cn in cns if cn in self.by_cn]
        if cns:
            self.remove_rows(cns)
            set_label(self.status, f"Đã bỏ qua: {', '.join(cns[:5])}{'…' if len(cns) > 5 else ''}", OK_GREEN)

    def copy_chinese(self):
        if not self.current:
            return
        QGuiApplication.clipboard().setText(self.current)
        self.vi_entry.setFocus()
        self.vi_entry.selectAll()
        set_label(self.status, f"Đã copy chữ Hán: {self.current}", OK_GREEN)

    def add_current(self):
        cn = self.current
        if not cn:
            return
        vi_text = self.edited[cn].strip()
        if not vi_text:
            warn(self, "Chú ý", "Vui lòng nhập tên tiếng Việt!")
            return
        temporary = self.temp_box.isChecked()
        if self.app.add_names([(cn, vi_text)], temporary, parent=self):
            self.remove_rows([cn])
            set_label(self.status, f"✅ Đã thêm{' name tạm' if temporary else ''}: {cn} = {vi_text}", OK_GREEN)
            self.tree.setFocus()

    def focus_vi(self):
        if self.current:
            self.vi_entry.setFocus()
            self.vi_entry.selectAll()

    def tree_step(self, delta):
        self.tree.setFocus()
        index = self.tree.indexOfTopLevelItem(self.tree.currentItem()) if self.tree.currentItem() else -1
        target = self.tree.topLevelItem(max(0, min(self.tree.topLevelItemCount() - 1, index + delta)))
        if target is not None:
            self.tree.setCurrentItem(target)

    # ── thêm thủ công ──

    def on_manual_cn(self, text):
        cn = unicodedata.normalize("NFC", text.strip())
        if not cn:
            set_label(self.manual_info, "", MUTED)
            return
        hits = self.source_text.count(cn)
        known = cn in self.app.load_name_config() or cn in self.app.temp_names
        set_label(self.manual_info, ("đã có trong name · " if known else "") + f"{hits} lần trong bài",
                  WARN if known else (MUTED if hits else ERROR))
        suggestion = self.app._suggest_vi(cn)
        if self.manual_vi.text().strip() in ("", self.manual_auto):
            self.manual_vi.setText(suggestion)
            self.manual_auto = suggestion

    def add_manual(self):
        cn = unicodedata.normalize("NFC", self.manual_cn.text().strip())
        vi = self.manual_vi.text().strip()
        if not cn or not vi:
            warn(self, "Chú ý", "Nhập cả chữ Hán và tên tiếng Việt.")
            return
        temporary = self.temp_box.isChecked()
        if self.app.add_names([(cn, vi)], temporary, parent=self):
            if cn in self.by_cn and cn not in self.ignored:
                self.remove_rows([cn])
            set_label(self.status, f"✅ Đã thêm{' name tạm' if temporary else ''} (thủ công): {cn} = {vi}", OK_GREEN)
            self.manual_cn.clear()
            self.manual_vi.clear()
            self.manual_auto = ""
            self.manual_cn.setFocus()

    def take_selection(self):
        """Bôi đen chữ Hán trong khung ngữ cảnh → điền vào ô thêm thủ công."""
        picked = self.context.textCursor().selectedText().strip()
        if picked and len(picked) <= 12 and all("\u3400" <= ch <= "\u9fff" or ch == "·" for ch in picked):
            self.manual_cn.setText(picked)
            self.manual_vi.setFocus()
            self.manual_vi.selectAll()

    # ── thêm theo lô ──

    def select_visible(self, value):
        for cn in list(self.items):
            if value and self.edited[cn].strip():
                self.selected.add(cn)
            elif not value:
                self.selected.discard(cn)
            self.refresh_row(cn, counts=False)
        self.update_counts()

    def add_selected(self):
        entries = [(c["cn"], self.edited[c["cn"]].strip()) for c in self.candidates
                   if c["cn"] in self.selected and c["cn"] not in self.ignored and self.edited[c["cn"]].strip()]
        missing = sum(1 for cn in self.selected if cn not in self.ignored and not self.edited[cn].strip())
        if not entries:
            warn(self, "Chú ý", "Chưa chọn tên nào có bản dịch tiếng Việt.")
            return
        temporary = self.temp_box.isChecked()
        if not self.app.add_names(entries, temporary, parent=self):
            return
        self.remove_rows([cn for cn, _vi in entries])
        suffix = f"; bỏ qua {missing} mục trống" if missing else ""
        set_label(self.status, f"✅ Đã lưu {len(entries)} tên vào {'name tạm' if temporary else 'name.cfg'}{suffix}",
                  OK_GREEN)


class _ScanEntry(LineEdit):
    """Ô "Bản dịch" của Scan Names: Enter thêm, Esc về bảng, ↑↓ đi dòng, F2 đổi gợi ý."""

    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog

    def keyPressEvent(self, event):
        key, d = event.key(), self.dialog
        if key in (Qt.Key_Return, Qt.Key_Enter):
            d.add_current()
        elif key == Qt.Key_Escape:
            d.tree.setFocus()
        elif key == Qt.Key_Down:
            d.tree_step(1)
        elif key == Qt.Key_Up:
            d.tree_step(-1)
        elif key == Qt.Key_F2:
            d.swap_sources()
        else:
            super().keyPressEvent(event)


# ═════════════════════════ Name tạm & R2 ═════════════════════════

class TempNamesDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("🏷 Name tạm — chỉ dùng cho lượt dịch này")
        restore_geometry(self, "builder_temp_names", 540, 460)
        self.setMinimumSize(420, 360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(label("Áp dụng cho lần dịch / dịch lại tiếp theo, không ghi vào name.cfg.\n"
                            "Tự xoá sau khi Lưu data.json hoặc Lưu vào thư viện."))
        self.ent_cn, self.ent_vi = LineEdit(), LineEdit()
        self.ent_cn.setFixedWidth(130)
        lay.addLayout(hbox(self.ent_cn, label("="), (self.ent_vi, 1), button("➕ Thêm", self.add, "#8a5a22")))
        self.listbox = QListWidget()
        self.listbox.setSelectionMode(QAbstractItemView.ExtendedSelection)
        lay.addWidget(self.listbox, 1)
        self.status = label("", MUTED)
        lay.addWidget(self.status)
        lay.addLayout(hbox(button("Xoá mục chọn", self.remove_selected), button("Xoá hết", self.clear_all, "#5a2a24"),
                           "stretch", button("💾 Lưu vĩnh viễn vào name.cfg", self.make_permanent, ACCENT),
                           button("Đóng", self.reject)))
        self.ent_cn.returnPressed.connect(self.ent_vi.setFocus)
        self.ent_vi.returnPressed.connect(self.add)
        self.listbox.itemSelectionChanged.connect(self.on_select)
        QShortcut(QKeySequence("Delete"), self.listbox, self.remove_selected, context=Qt.WidgetShortcut)
        self.keys = []
        self.refresh()
        self.ent_cn.setFocus()

    def done(self, code):
        save_geometry(self, "builder_temp_names")
        super().done(code)

    def picked(self):
        return [self.keys[self.listbox.row(item)] for item in self.listbox.selectedItems()]

    def refresh(self):
        self.keys = sorted(self.app.temp_names)
        self.listbox.clear()
        self.listbox.addItems([f"{cn}  =  {self.app.temp_names[cn]}" for cn in self.keys])
        self.status.setText(f"{len(self.keys)} name tạm" if self.keys else "Chưa có name tạm nào.")

    def add(self):
        cn, vi = self.ent_cn.text().strip(), self.ent_vi.text().strip()
        if not cn or not vi:
            warn(self, "Chú ý", "Nhập cả chữ Hán và tên tiếng Việt.")
            return
        if self.app.add_temp_names([(cn, vi)], parent=self):
            self.ent_cn.clear()
            self.ent_vi.clear()
            self.ent_cn.setFocus()
            self.refresh()

    def on_select(self):
        picked = self.picked()
        if len(picked) == 1:   # chọn một dòng để sửa: nạp lên ô nhập
            self.ent_cn.setText(picked[0])
            self.ent_vi.setText(self.app.temp_names[picked[0]])

    def remove_selected(self):
        for cn in self.picked():
            self.app.temp_names.pop(cn, None)
        self.app.refresh_temp_names_button()
        self.refresh()

    def make_permanent(self):
        picked = self.picked() or list(self.keys)
        if picked and self.app.add_names([(cn, self.app.temp_names[cn]) for cn in picked], False, parent=self):
            self.refresh()
            self.status.setText(f"✅ Đã lưu {len(picked)} name vào name.cfg")

    def clear_all(self):
        if self.app.temp_names and ask_yes_no(self, "Xoá name tạm", "Xoá hết name tạm?"):
            self.app.clear_temp_names()
            self.refresh()


class R2Dialog(QDialog):
    """Khoá API R2 (lưu ngoài repo) + đồng bộ / khôi phục truyện bằng tay."""
    ROWS = (("account_id", "Account ID", False), ("access_key_id", "Access Key ID", False),
            ("secret_access_key", "Secret Access Key", True), ("bucket", "Bucket", False))

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.busy = False
        self.setWindowTitle("☁ Cloudflare R2 — nơi lưu truyện cho trang web")
        self.creds = r2_store.load_credentials() or {}
        grid = QGridLayout(self)
        grid.setContentsMargins(14, 12, 14, 14)
        grid.addWidget(label("Truyện lưu xong được tự đẩy lên R2 (không commit/push). Khoá API: R2 → Manage API tokens,\n"
                             "quyền Object Read & Write, chỉ bucket của trang. Khoá chỉ lưu trên máy này.", MUTED, 9),
                       0, 0, 1, 2)
        self.fields = {}
        for i, (key, text, secret) in enumerate(self.ROWS, start=1):
            grid.addWidget(label(text, "#e0d6c6", 9), i, 0)
            entry = LineEdit("" if secret else self.creds.get(key, "stv-library" if key == "bucket" else ""))
            entry.setMinimumWidth(420)
            entry.setStyleSheet("font-family: Consolas;")
            if secret:
                entry.setEchoMode(QLineEdit.EchoMode.Password)
            grid.addWidget(entry, i, 1)
            self.fields[key] = entry
        if self.creds.get("secret_access_key"):
            grid.addWidget(label("(để trống ô Secret = giữ khoá đã lưu)", HINT, 8), 5, 1)
        self.status = label(f"Cấu hình: {r2_store.config_path()}" if self.creds else "Chưa cấu hình.", OK_GREEN, 9, wrap=True)
        grid.addWidget(self.status, 6, 0, 1, 2)
        grid.addLayout(hbox(button("Lưu & kiểm tra", self.save_and_check, "#46734f", bold=True),
                            button("Đồng bộ ngay", self.sync_now, "#6a5683", bold=True),
                            button("Xoá file thừa", self.prune, "#8a372e", bold=True), "stretch",
                            button("Tải truyện từ R2 về", self.restore, bold=True)), 7, 0, 1, 2)

    def run(self, text, job, done):
        if self.busy:
            return
        self.busy = True
        self.status.setText(text)

        def work():
            try:
                message = job()
            except Exception as exc:
                message = f"⚠ {exc}"
            self.app.bridge.call(self._finish, message, done)
        threading.Thread(target=work, daemon=True).start()

    def _finish(self, message, done):
        self.busy = False
        self.status.setText(message)
        done(message)

    def save_and_check(self):
        values = {k: e.text().strip() for k, e in self.fields.items()}
        if not values["secret_access_key"]:
            values["secret_access_key"] = self.creds.get("secret_access_key", "")
        if not all(values.values()):
            self.status.setText("⚠ Điền đủ 4 ô.")
            return

        def job():
            r2_store.R2Client(values).check()          # thử ghi + xoá một file nhỏ
            r2_store.save_credentials(**values)
            return "✅ Kết nối được và đã lưu khoá. Bấm “Đồng bộ ngay” để đẩy truyện lên."

        def saved(message):
            if not message.startswith("✅"):
                return
            self.creds.update(values)
            # Xoá cảnh báo "chưa cấu hình" cũ trên thanh trạng thái và đẩy ngay phần còn chờ.
            self.app.set_status("R2: đã lưu khoá — đang đồng bộ truyện lên R2…")
            r2_store.reset_unconfigured_warning()
            r2_store.request_sync(BASE_DIR)
        self.run("Đang kiểm tra kết nối…", job, saved)

    def sync_now(self, mass=False):
        if not r2_store.load_credentials():
            self.status.setText("⚠ Chưa có khoá: lưu khoá trước.")
            return

        def job():
            client = r2_store.R2Client(r2_store.load_credentials())
            result = r2_store.sync(BASE_DIR, client, lambda m: self.app.bridge.call(self.status.setText, m),
                                   allow_mass_delete=mass)
            if result.errors:
                return f"⚠ {result.summary()} — {result.errors[0]}"
            if result.held_deletes:
                return (f"⚠ {result.summary()}. Có {len(result.held_deletes)} file trên R2 không còn trên máy "
                        "(vd. {}) — kiểm tra rồi bấm “Xoá file thừa”.".format(result.held_deletes[0]))
            return f"✅ R2: {result.summary()}."
        self.run("Đang đồng bộ… (lần đầu đẩy toàn bộ truyện, có thể mất vài phút)", job,
                 lambda m: self.app.set_status(m.replace("✅ ", ""), ERROR if m.startswith("⚠") else None))

    def prune(self):
        if ask_yes_no(self, "Xoá file thừa trên R2", "Xoá trên R2 mọi chương/truyện không còn trong thư mục "
                                                    "trên máy?\nKhông hoàn tác được.", default_no=True, warning=True):
            self.sync_now(mass=True)

    def restore(self):
        if not ask_yes_no(self, "Tải truyện từ R2 về",
                          f"Tải mọi truyện trên R2 về {BASE_DIR}?\nFile đã có trên máy được giữ nguyên."):
            return

        def job():
            count, errors = r2_store.restore(BASE_DIR, progress=lambda m: self.app.bridge.call(self.status.setText, m))
            if errors:
                return f"⚠ Đã ghi {count} file, {len(errors)} lỗi (vd. {errors[0]})."
            return f"✅ Đã ghi {count} file."
        self.run("Đang tải từ R2 về…", job, lambda m: None)


# ═════════════════════════ Cửa sổ chính ═════════════════════════

class TranslatorWindow(QWidget, core.TranslatorCore):
    def __init__(self, embedded=False):
        """embedded: nằm trong studio_qt.py (cửa sổ, kích thước do app chứa quản lý)."""
        QWidget.__init__(self)
        core.TranslatorCore.__init__(self)
        self.embedded = embedded
        self.bridge = UiBridge(self)
        self.reviews = []
        self._worker = None
        self._cancel_event = None
        self._busy = False
        if not embedded:
            self.setWindowTitle("Story Translator Pro - SangTacViet API")
            restore_geometry(self, "builder_main", 760, 640)
        self.setAcceptDrops(True)
        self.setup_ui()
        self._count_timer = QTimer(self, singleShot=True, interval=400)
        self._count_timer.timeout.connect(self.update_counter)
        self.txt_area.textChanged.connect(self._count_timer.start)
        self._progress_anim = QVariantAnimation(self, duration=450, easingCurve=QEasingCurve.OutCubic)
        self._progress_anim.valueChanged.connect(lambda v: self.progress.setValue(int(v)))

        # Kết quả đồng bộ R2 chạy nền hiện trên thanh trạng thái (lỗi màu đỏ); mở app thì đẩy nốt
        # phần lần trước chưa lên được (mất mạng, tắt app giữa chừng…).
        r2_store.add_listener(lambda message, ok: self.bridge.call(self.set_status, message, None if ok else ERROR))
        r2_store.request_sync(BASE_DIR)
        # Nạp sẵn model quét tên đã có trên máy để lần Scan Names đầu không phải chờ (STV_NER_PRELOAD=0 để tắt).
        if (core._NAME_SCANNER_OK or core._MOXHI_OK) and os.environ.get("STV_NER_PRELOAD", "1") != "0":
            QTimer.singleShot(1500, lambda: threading.Thread(target=self.preload_name_model,
                                                             name="name-preload", daemon=True).start())

    # ── giao diện ──

    def setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 8)
        title = label("DỊCH TRUYỆN TRUNG - VIỆT", "#f4ede1", 14, True)
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        self.ent_title = LineEdit()
        lay.addLayout(hbox(label("Tên truyện:"), (self.ent_title, 1)))
        self.lbl_counter = label("", "#8a7f70", 9)
        lay.addLayout(hbox(label("Nội dung tiếng Trung:"), "stretch", self.lbl_counter, margins=(0, 8, 0, 0)))
        self.txt_area = PlainTextEdit()
        self.txt_area.setAcceptDrops(False)   # file thả vào đâu cũng do cửa sổ xử lý
        self.txt_area.setStyleSheet(f"QPlainTextEdit {{ font-family: '{CN_FONT}'; font-size: 11pt; padding: 6px; }}")
        self.find_bar = FindBar(self.txt_area, self)
        lay.addWidget(self.find_bar)
        lay.addWidget(self.txt_area, 1)

        self.drop_zone = QLabel("📂  Kéo thả file .txt vào đây")
        self.drop_zone.setAlignment(Qt.AlignCenter)
        self._drop_style(False)
        lay.addWidget(self.drop_zone)

        self.btn_file = button("📁 Chọn File .txt", self.load_file)
        self.btn_scan = button("🔍 Scan Names", self.open_scan_names_dialog, "#6a5683")
        self.btn_draft = button("📝 Mở nháp", self.open_draft)
        self.btn_temp_names = button("🏷 Name tạm", lambda: TempNamesDialog(self).exec())
        self.btn_r2 = button("☁ R2", lambda: R2Dialog(self).exec())
        self.btn_clear = button("🗑️ Xóa tất cả", self.clear_all, "#9a3f35")
        self.btn_cancel = button("⏹ Huỷ", self.cancel_translation, "#8a372e")
        self.btn_run = button("🚀 Bắt đầu dịch", self.start_thread, ACCENT, bold=True)
        self.btn_clear.hide()
        self.btn_cancel.hide()
        lay.addLayout(hbox(self.btn_file, self.btn_scan, self.btn_draft, self.btn_temp_names, self.btn_r2, "stretch",
                           self.btn_clear, self.btn_cancel, self.btn_run, margins=(0, 6, 0, 0)))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setRange(0, 1000)
        holder = QWidget()   # giữ chỗ cố định: thanh hiện/ẩn không làm co giãn ô nội dung
        holder.setFixedHeight(14)
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 3, 0, 3)
        hl.addWidget(self.progress)
        self.progress.hide()
        lay.addWidget(holder)
        self.lbl_status = label("Sẵn sàng  ·  Ctrl+Enter để dịch", "#8a7f70")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_status)

        # Chỉ có hiệu lực khi đang ở trang này (studio có 2 trang cùng phím tắt).
        ctx = Qt.WidgetWithChildrenShortcut
        for keys, slot in (("Ctrl+Return", self.start_thread), ("Ctrl+Enter", self.start_thread),
                           ("Ctrl+F", self.find_bar.open_bar), ("F3", lambda: self.find_bar.step(1)),
                           ("Shift+F3", lambda: self.find_bar.step(-1)), ("Ctrl+O", self.load_file)):
            QShortcut(QKeySequence(keys), self, slot, context=ctx)
        QShortcut(QKeySequence("Escape"), self.txt_area,
                  lambda: self.find_bar.isVisible() and self.find_bar.close_bar(), context=Qt.WidgetShortcut)

    def _drop_style(self, active):
        self.drop_zone.setStyleSheet(
            f"QLabel {{ background: {FIELD if active else PANEL}; color: {'#d9a35c' if active else '#8a7f70'}; "
            f"border: 2px dashed {'#d9a35c' if active else '#3a332c'}; border-radius: 4px; padding: 12px; }}")

    def set_status(self, text, color=None):
        set_label(self.lbl_status, text, color)

    def report_status(self, text):   # TranslatorCore gọi từ luồng nền
        self.bridge.call(self.set_status, text)

    def update_counter(self):
        self.lbl_counter.setText(core.counter_text(raw_text(self.txt_area)))

    # ── kéo thả / mở file ──

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_style(True)

    def dragLeaveEvent(self, event):
        self._drop_style(False)

    def dropEvent(self, event):
        self._drop_style(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        txt_files = [p for p in paths if p.lower().endswith(".txt")]
        if not txt_files:
            warn(self, "Chú ý", "Chỉ hỗ trợ file .txt!")
            return
        event.acceptProposedAction()
        self._load_from_path(txt_files[0])
        if len(txt_files) > 1:
            self.set_status(f"Đã tải {os.path.basename(txt_files[0])} (bỏ qua {len(txt_files) - 1} file còn lại)", WARN)

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file truyện", "", "Text files (*.txt)")
        if path:
            self._load_from_path(path)

    def _load_from_path(self, file_path):
        try:
            text, encoding = store.read_text_file(file_path)
        except Exception as exc:
            error(self, "Lỗi", f"Không thể đọc file:\n{exc}")
            return
        self.txt_area.setPlainText(text)
        self.ent_title.setText(os.path.splitext(os.path.basename(file_path))[0])
        self.set_status(f"Đã tải: {os.path.basename(file_path)}  ·  mã hoá {encoding}",
                        WARN if "lỗi" in encoding else OK_GREEN)
        self.update_counter()

    def open_draft(self):
        os.makedirs(core.DRAFT_DIR, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Mở bản nháp", core.DRAFT_DIR, "Bản nháp (*.json)")
        if not path:
            return
        try:
            title, slug, cn, vi, stamp = core.read_draft(path)
        except Exception as exc:
            error(self, "Lỗi", f"Không mở được nháp:\n{exc}")
            return
        self.btn_run.setEnabled(False)
        self.btn_clear.hide()
        self.set_status(f"Đang xem nháp: {title} ({stamp})", WARN)
        ReviewWindow(self, title, slug, cn, vi, from_draft=True)

    def clear_all(self):
        self.ent_title.clear()
        self.txt_area.clear()
        self.clear_temp_names()   # truyện mới: name tạm của truyện cũ không còn dùng
        self.set_status("Sẵn sàng", "#8a7f70")
        self.btn_clear.hide()

    def review_closed(self):
        """Một cửa sổ Review vừa đóng: mở lại nút dịch."""
        if not self.reviews and not self._busy:
            self.btn_run.setEnabled(True)
            self.btn_clear.show()
            if not self.lbl_status.text().startswith(("✅", "📚")):
                self.set_status("Sẵn sàng", "#8a7f70")

    # ── name tạm ──

    def add_temp_names(self, entries, parent=None):
        try:
            self.merge_temp_names(entries)
        except ValueError as exc:
            error(parent or self, "Name tạm không hợp lệ", str(exc))
            return False
        self.refresh_temp_names_button()
        return True

    def clear_temp_names(self):
        count = len(self.temp_names)
        self.temp_names.clear()
        self.refresh_temp_names_button()
        return count

    def refresh_temp_names_button(self):
        count = len(self.temp_names)
        self.btn_temp_names.setText(f"🏷 Name tạm ({count})" if count else "🏷 Name tạm")
        self.btn_temp_names.setStyleSheet("QPushButton { background: #8a5a22; }" if count else "")

    def add_names(self, entries, temporary, parent=None):
        """Thêm vào name tạm hoặc name.cfg tuỳ lựa chọn của người dùng."""
        if temporary:
            return self.add_temp_names(entries, parent=parent)
        try:
            self.save_names_to_cfg(entries)
        except Exception as exc:
            error(parent or self, "Lỗi", f"Không thể ghi name.cfg:\n{exc}")
            return False
        self.refresh_temp_names_button()
        return True

    # ── Scan Names ──

    def open_scan_names_dialog(self):
        text = raw_text(self.txt_area).strip()
        if not text:
            warn(self, "Chú ý", "Vui lòng nhập nội dung tiếng Trung trước!")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("⏳ Đang quét...")
        known_temp = set(self.temp_names)

        def worker():
            try:
                found, warning = self.scan_names_with_suggestions(
                    text, known_temp, on_progress=lambda msg: self.bridge.call(self.set_status, msg))
                self.bridge.call(done, found, warning, None)
            except Exception as exc:
                self.bridge.call(done, None, None, exc)

        def done(candidates, api_warning, err):
            QApplication.restoreOverrideCursor()
            self.btn_scan.setEnabled(True)
            self.btn_scan.setText("🔍 Scan Names")
            if err:
                error(self, "Lỗi", f"Lỗi khi quét tên:\n{err}")
                return
            note = getattr(self, "_scan_note", "")
            self.set_status(f"Đã quét xong: tìm thấy {len(candidates)} ứng viên" + (f" · ⚠ {note}" if note else ""),
                            WARN if note else None)
            if api_warning:
                warn(self, "Không tự dịch được tên",
                     f"Tên người vẫn có gợi ý Hán-Việt; mục còn trống có thể dùng nút Copy Hán để tra.\n\n{api_warning}")
            dlg = ScanNamesDialog(self, candidates)
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            dlg.show()

        threading.Thread(target=worker, daemon=True).start()

    # ── dịch ──

    def _set_busy(self, busy):
        self._busy = busy
        if busy:
            self.btn_run.setEnabled(False)
            self.btn_clear.hide()
            self.btn_cancel.setEnabled(True)
            self.btn_cancel.setText("⏹ Huỷ")
            self.btn_cancel.show()
            self._progress_anim.stop()
            self.progress.setValue(0)
            self.progress.show()
        else:
            self.btn_cancel.hide()
            self._progress_anim.stop()
            self.progress.hide()

    def cancel_translation(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("Đang dừng…")
            self.set_status("Đang dừng sau đợt hiện tại…", WARN)

    def start_thread(self):
        if self._worker is not None and self._worker.is_alive():
            return
        if self.reviews:
            self.reviews[-1].raise_()
            self.reviews[-1].activateWindow()
            return
        title = self.ent_title.text().strip()
        content = raw_text(self.txt_area).strip()
        if not title or not content:
            warn(self, "Chú ý", "Vui lòng nhập tiêu đề và nội dung!")
            return
        slug = core.slugify_vn(title)
        if not slug:
            warn(self, "Chú ý", "Tiêu đề không hợp lệ, không thể tạo slug!")
            return
        self._cancel_event = threading.Event()
        self._set_busy(True)
        self.set_status(f"Slug: {slug} — Đang xử lý dữ liệu...", "#d9a35c")
        # Chụp name tạm trên luồng chính; luồng nền không đọc trạng thái giao diện.
        self._worker = threading.Thread(target=self.run_process,
                                        args=(title, slug, content, self._cancel_event, dict(self.temp_names)),
                                        daemon=True)
        self._worker.start()

    def _update_progress(self, done, total, started):
        total = max(total, 1)
        # +0.5: thanh nhích lên trong lúc chờ API của đợt hiện tại, không đứng im rồi nhảy một mạch.
        target = min(done + 0.5, total) / total * 1000
        self._progress_anim.stop()
        self._progress_anim.setStartValue(float(self.progress.value()))
        self._progress_anim.setEndValue(float(target))
        self._progress_anim.start()
        text = f"Đang dịch đợt {min(done + 1, total)}/{total}"
        if done:
            remaining = (time.time() - started) / done * (total - done)
            text += f" · còn ~{remaining / 60:.0f} phút" if remaining >= 90 else f" · còn ~{remaining:.0f} giây"
        self.set_status(text + "...", "#d9a35c")

    def run_process(self, title, slug, content, cancel, temp_names=None):
        """Luồng nền: không chạm widget, mọi cập nhật qua bridge."""
        try:
            cn_lines, vi_lines, total = self.translate_story(
                content, cancel, temp_names,
                on_progress=lambda i, n, started: self.bridge.call(self._update_progress, i, n, started))
            self.bridge.call(self._translation_finished, title, slug, cn_lines, vi_lines, cancel.is_set(), total)
        except Exception as exc:
            self.bridge.call(self._translation_failed, exc)

    def _translation_failed(self, exc):
        self._set_busy(False)
        self.btn_run.setEnabled(True)
        self.btn_clear.show()
        self.set_status("❌ Lỗi khi dịch", ERROR)
        error(self, "Lỗi", f"Lỗi khi dịch:\n{exc}")

    def _translation_finished(self, title, slug, cn_lines, vi_lines, cancelled, total):
        self._set_busy(False)
        if cancelled:
            if cn_lines and ask_yes_no(self, "Đã huỷ", f"Đã dịch {len(cn_lines)}/{total} đoạn trước khi huỷ.\n"
                                                       "Mở Review với phần đã dịch?"):
                self.set_status(f"Đã huỷ — xem {len(cn_lines)}/{total} đoạn đã dịch", WARN)
                ReviewWindow(self, title, slug, cn_lines, vi_lines)
            else:
                self.btn_run.setEnabled(True)
                self.btn_clear.show()
                self.set_status("Đã huỷ dịch.", WARN)
            return
        self.set_status("Hoàn tất dịch API. Đang mở cửa sổ Review...", WARN)
        ReviewWindow(self, title, slug, cn_lines, vi_lines)

    # ── đóng ──

    def can_close(self):
        """False nếu còn cửa sổ Review hoặc người dùng không muốn bỏ bản đang dịch."""
        if self.reviews:
            self.reviews[0].raise_()
            warn(self.reviews[0], "Còn cửa sổ Review",
                 "Hãy đóng cửa sổ Review bản dịch trước để lưu hoặc giữ nháp.")
            return False
        if self._worker is not None and self._worker.is_alive():
            if not ask_yes_no(self, "Đang dịch", "Bản dịch đang chạy. Thoát và bỏ phần đang dịch?",
                              default_no=True, warning=True):
                return False
            self._cancel_event.set()
        return True

    def closeEvent(self, event):
        if not self.can_close():
            event.ignore()
            return
        if not self.embedded:
            save_geometry(self, "builder_main")
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Story Translator")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = TranslatorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
