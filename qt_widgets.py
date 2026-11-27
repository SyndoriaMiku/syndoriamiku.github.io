"""Thành phần Qt dùng chung (builder.py, editor.py, studio.py): theme tối, ô nhập gõ IME tốt,
thanh tìm kiếm, hộp thoại, lưu vị trí cửa sổ, chuyển việc từ luồng nền về luồng giao diện."""
import re

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QInputMethodEvent, QKeySequence, QShortcut, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTextEdit, QWidget)

import translator_core as core
from translator_core import BG, PANEL, FIELD, MUTED, TEXT

ACCENT = "#9c6a28"
OK_GREEN = "#8fc29a"
WARN = "#e0b25c"
ERROR = "#e8857b"
HINT = "#6b6255"

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI'; font-size: 10pt; }}
QLabel {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {PANEL}; color: #f4ede1; border: 1px solid #3a332c; border-radius: 3px; padding: 4px;
    selection-background-color: {ACCENT}; selection-color: white; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: #8a6a3a; }}
QComboBox QAbstractItemView {{ background: {FIELD}; color: white; selection-background-color: {ACCENT}; }}
QPushButton {{ background: {FIELD}; color: white; border: none; border-radius: 3px; padding: 6px 14px; }}
QPushButton:hover {{ background: #3a332c; }}
QPushButton:disabled {{ color: #6b6255; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 13px; height: 13px; border: 1px solid #7a6f60;
    background: {FIELD}; }}
QCheckBox::indicator {{ border-radius: 2px; }}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: #d9a35c; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: #d9a35c; }}
QTreeWidget, QListWidget {{ background: {PANEL}; alternate-background-color: #221e19; border: none;
    selection-background-color: #4f3f63; selection-color: white; outline: 0; }}
QHeaderView::section {{ background: {FIELD}; color: {MUTED}; border: none; padding: 5px; font-weight: bold; }}
QProgressBar {{ background: {PANEL}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QScrollBar:vertical {{ background: {BG}; width: 12px; }}
QScrollBar::handle:vertical {{ background: #3a332c; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 12px; }}
QScrollBar::handle:horizontal {{ background: #3a332c; border-radius: 5px; min-width: 24px; }}
QMenu {{ background: {FIELD}; color: white; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QMenu::item:disabled {{ color: #6b6255; }}
QToolTip {{ background: {FIELD}; color: white; border: 1px solid #4a4238; }}
"""


# ───────────────────────── gõ IME ─────────────────────────

def plain_preedit(event):
    """Bỏ gạch chân (và mọi định dạng) bộ gõ gắn cho chữ đang gõ dở; giữ con trỏ và chữ đã chốt."""
    attrs = []
    for a in event.attributes():
        if a.type == QInputMethodEvent.TextFormat:
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.NoUnderline)
            a = QInputMethodEvent.Attribute(a.type, a.start, a.length, fmt)
        attrs.append(a)
    clean = QInputMethodEvent(event.preeditString(), attrs)
    clean.setCommitString(event.commitString(), event.replacementStart(), event.replacementLength())
    return clean


class LineEdit(QLineEdit):
    def inputMethodEvent(self, event):
        super().inputMethodEvent(plain_preedit(event))


class PlainTextEdit(QPlainTextEdit):
    def inputMethodEvent(self, event):
        super().inputMethodEvent(plain_preedit(event))


def raw_text(edit):
    """Nội dung ô văn bản, giữ nguyên ký tự (toPlainText đổi nbsp thành dấu cách)."""
    return edit.document().toRawText().replace(" ", "\n")


def selected_text(edit):
    return edit.textCursor().selectedText().replace(" ", "\n")


def py_offset(text, qt_pos):
    """Vị trí QTextDocument (UTF-16) → chỉ số Python trong text."""
    if all(ord(ch) <= 0xFFFF for ch in text):
        return qt_pos
    units = 0
    for i, ch in enumerate(text):
        if units >= qt_pos:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def qt_offsets(text):
    """Hàm đổi chỉ số Python → vị trí QTextDocument (UTF-16): khác nhau khi có ký tự ngoài BMP."""
    if all(ord(ch) <= 0xFFFF for ch in text):
        return lambda i: i
    return lambda i: len(text[:i].encode("utf-16-le")) // 2


# ───────────────────────── luồng nền → giao diện ─────────────────────────

class UiBridge(QObject):
    """call(func, *args) an toàn từ mọi luồng: func chạy trên luồng giao diện."""
    _run = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._run.connect(self._invoke, Qt.QueuedConnection)

    def call(self, func, *args):
        self._run.emit(lambda: func(*args))

    @staticmethod
    def _invoke(job):
        try:
            job()
        except Exception as error:  # không để một callback hỏng làm sập app
            core.log(f"UI callback error: {error}")


# ───────────────────────── hộp thoại ─────────────────────────

def info(parent, title, text):
    QMessageBox.information(parent, title, text)


def warn(parent, title, text):
    QMessageBox.warning(parent, title, text)


def error(parent, title, text):
    QMessageBox.critical(parent, title, text)


def ask_yes_no(parent, title, text, default_no=False, warning=False):
    box = QMessageBox(QMessageBox.Warning if warning else QMessageBox.Question, title, text,
                      QMessageBox.Yes | QMessageBox.No, parent)
    box.button(QMessageBox.Yes).setText("Có")
    box.button(QMessageBox.No).setText("Không")
    box.setDefaultButton(QMessageBox.No if default_no else QMessageBox.Yes)
    return box.exec() == QMessageBox.Yes


def ask_yes_no_cancel(parent, title, text):
    """True / False / None (Hủy)."""
    box = QMessageBox(QMessageBox.Warning, title, text,
                      QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, parent)
    box.button(QMessageBox.Yes).setText("Có")
    box.button(QMessageBox.No).setText("Không")
    box.button(QMessageBox.Cancel).setText("Hủy")
    result = box.exec()
    return {QMessageBox.Yes: True, QMessageBox.No: False}.get(result)


def button(text, slot=None, color=None, fg="white", bold=False, small=False):
    btn = QPushButton(text)
    css = []
    if color:
        css.append(f"QPushButton {{ background: {color}; color: {fg}; }}"
                   f"QPushButton:hover {{ background: {QColor(color).lighter(118).name()}; }}")
    elif fg != "white":
        css.append(f"QPushButton {{ color: {fg}; }}")
    if bold or small:
        css.append("QPushButton {" + ("font-weight: bold;" if bold else "")
                   + ("padding: 3px 10px; font-size: 9pt;" if small else "") + "}")
    if css:
        btn.setStyleSheet("".join(css))
    btn.setCursor(Qt.PointingHandCursor)
    btn.setAutoDefault(False)   # Enter trong ô nhập của hộp thoại không được bấm nhầm nút
    if slot is not None:
        btn.clicked.connect(lambda _checked=False: slot())
    return btn


def label(text="", color=MUTED, size=None, bold=False, wrap=False):
    lab = QLabel(text)
    css = f"color: {color};" + (f"font-size: {size}pt;" if size else "") + ("font-weight: bold;" if bold else "")
    lab.setStyleSheet(css)
    lab.setWordWrap(wrap)
    return lab


def set_label(lab, text, color=None):
    lab.setText(text)
    if color:
        css = re.sub(r"color:\s*[^;]+;", "", lab.styleSheet())
        lab.setStyleSheet(f"color: {color};" + css)


# ───────────────────────── vị trí cửa sổ ─────────────────────────

def restore_geometry(widget, key, width, height):
    """Đặt lại kích thước/vị trí đã lưu (khoá "qt_<key>" trong editor_config.json)."""
    saved = core.load_config().get(f"qt_{key}")
    if saved:
        try:
            if widget.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii"))):
                return
        except Exception:
            pass
    widget.resize(width, height)


def save_geometry(widget, key):
    core.save_config({f"qt_{key}": bytes(widget.saveGeometry().toBase64()).decode("ascii")})


# ───────────────────────── thanh tìm kiếm ─────────────────────────

class FindBar(QWidget):
    """Tìm trong một QPlainTextEdit: chuỗi thường hoặc regex, Aa, ▲▼, nhớ vị trí:
    mở thì bắt đầu từ chỗ con trỏ/đoạn bôi đen, đóng thì bôi đen kết quả đang xem."""
    LIMIT = 5000

    def __init__(self, edit, parent=None):
        super().__init__(parent)
        self.edit = edit
        self.matches = []      # [(start, end)] vị trí trong tài liệu
        self.index = -1
        self.setStyleSheet(f"background: {FIELD};")
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(8, 4, 6, 4)
        self.rows.setSpacing(4)
        row = self.row = QHBoxLayout()
        self.rows.addLayout(row)
        self.where = label("🔍")
        row.addWidget(self.where)
        self.entry = LineEdit()
        self.entry.setStyleSheet("font-family: Consolas; font-size: 10pt;")
        row.addWidget(self.entry, 1)
        self.regex = QCheckBox("Regex")
        self.case = QCheckBox("Aa")
        for box in (self.regex, self.case):
            box.setStyleSheet(f"color: {MUTED};")
            box.toggled.connect(lambda _on: self.refresh(keep_position=True))
            row.addWidget(box)
        self.status = label("", MUTED, 9)
        self.status.setMinimumWidth(80)
        self.status.setAlignment(Qt.AlignCenter)
        row.addWidget(self.status)
        for text, slot in (("▲", lambda: self.step(-1)), ("▼", lambda: self.step(1))):
            row.addWidget(button(text, slot, "#3a332c", small=True))
        self.close_btn = button("✕", self.close_bar, "#9a3f35", small=True)
        row.addWidget(self.close_btn)

        self._timer = QTimer(self, singleShot=True, interval=150)
        self._timer.timeout.connect(self.refresh)
        self._edit_timer = QTimer(self, singleShot=True, interval=300)
        self._edit_timer.timeout.connect(lambda: self.refresh(keep_position=True))
        self.entry.textChanged.connect(lambda _t: self._timer.start())
        self.entry.returnPressed.connect(lambda: self.step(1))
        QShortcut(QKeySequence("Shift+Return"), self.entry, lambda: self.step(-1), context=Qt.WidgetShortcut)
        QShortcut(QKeySequence("Escape"), self.entry, self.close_bar, context=Qt.WidgetShortcut)
        self.edit = None
        self.set_edit(edit)
        self.hide()

    def set_edit(self, edit):
        """Đổi ô văn bản đang tìm (xoá tô sáng ở ô cũ)."""
        if edit is self.edit:
            return
        if self.edit is not None:
            self.edit.setExtraSelections([])
            self.edit.textChanged.disconnect(self._on_edit_changed)
        self.edit = edit
        self.matches, self.index = [], -1
        edit.textChanged.connect(self._on_edit_changed)

    def pattern(self):
        """Regex đang tìm (None nếu ô trống); ném re.error nếu regex sai."""
        query = self.entry.text()
        if not query:
            return None
        return core.store.compile_search(query, regex=self.regex.isChecked(), match_case=self.case.isChecked())

    def current(self):
        return self.matches[self.index] if 0 <= self.index < len(self.matches) else None

    def _on_edit_changed(self):
        if self.isVisible() and self.entry.text():
            self._edit_timer.start()   # nội dung đổi: tìm lại, giữ gần kết quả đang xem

    def open_bar(self):
        cursor = self.edit.textCursor()
        picked = selected_text(self.edit)
        self.show()
        if picked and "\n" not in picked:
            cursor.setPosition(cursor.selectionStart())   # bắt đầu từ chính chỗ đang bôi đen
            self.edit.setTextCursor(cursor)
            self.entry.blockSignals(True)
            self.entry.setText(re.escape(picked) if self.regex.isChecked() else picked)
            self.entry.blockSignals(False)
        self.entry.setFocus()
        self.entry.selectAll()
        self.refresh()

    def close_bar(self):
        current = self.matches[self.index] if 0 <= self.index < len(self.matches) else None
        self.hide()
        self.matches, self.index = [], -1
        self.edit.setExtraSelections([])
        self.edit.setFocus()
        if current:   # giữ vị trí vừa tìm được: bôi đen để sửa/xoá ngay, mở lại tìm tiếp từ đây
            cursor = self.edit.textCursor()
            cursor.setPosition(current[0])
            cursor.setPosition(current[1], QTextCursor.KeepAnchor)
            self.edit.setTextCursor(cursor)
            self.edit.ensureCursorVisible()

    def refresh(self, keep_position=False, anchor=None):
        self._timer.stop()
        previous = self.matches[self.index][0] if keep_position and 0 <= self.index < len(self.matches) else None
        self.matches, self.index = [], -1
        try:
            pattern = self.pattern()
        except re.error:
            self.edit.setExtraSelections([])
            set_label(self.status, "Regex lỗi", ERROR)
            return
        if pattern is None:
            self.edit.setExtraSelections([])
            set_label(self.status, "", MUTED)
            return
        text = raw_text(self.edit)
        pos = qt_offsets(text)
        for match in pattern.finditer(text):
            if match.start() == match.end():
                continue   # regex khớp rỗng (vd. "a*") thì bỏ
            self.matches.append((pos(match.start()), pos(match.end())))
            if len(self.matches) >= self.LIMIT:
                break
        if not self.matches:
            self.edit.setExtraSelections([])
            set_label(self.status, "Không thấy", ERROR)
            return
        # Bắt đầu từ kết quả gần con trỏ (hoặc vị trí cũ khi nội dung vừa đổi).
        if anchor is None:
            anchor = previous if previous is not None else self.edit.textCursor().selectionStart()
        self.index = next((i for i, (start, _end) in enumerate(self.matches) if start >= anchor), 0)
        self._show_current(move_cursor=not keep_position)

    def step(self, direction):
        if not self.isVisible():
            self.open_bar()
            return
        if not self.matches:
            self.refresh()
            if not self.matches:
                return
        else:
            self.index = (self.index + direction) % len(self.matches)
        self._show_current()

    def _show_current(self, move_cursor=True):
        doc = self.edit.document()
        selections = []
        for i, (start, end) in enumerate(self.matches):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = QTextCursor(doc)
            sel.cursor.setPosition(start)
            sel.cursor.setPosition(end, QTextCursor.KeepAnchor)
            current = i == self.index
            sel.format.setBackground(QColor("#8a5a22" if current else "#6b4a1c"))
            sel.format.setForeground(QColor("#15130f" if current else "#f4ede1"))
            selections.append(sel)
        self.edit.setExtraSelections(selections)
        start, _end = self.matches[self.index]
        if move_cursor:
            cursor = self.edit.textCursor()
            cursor.setPosition(start)
            self.edit.setTextCursor(cursor)
            self.edit.ensureCursorVisible()
        more = "+" if len(self.matches) >= self.LIMIT else ""
        set_label(self.status, f"{self.index + 1}/{len(self.matches)}{more}", TEXT)
