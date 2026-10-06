"""Story Studio: dịch truyện (builder.py) và biên tập thư viện (editor.py) trong một cửa sổ.

Chạy: python studio.py   (hoặc pythonw studio.py để không hiện cửa sổ console)
builder.py và editor.py vẫn chạy riêng được như trước.
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

import tkinter as tk
from tkinter import messagebox
from tkinterdnd2 import TkinterDnD

import builder
import editor

TAB_BAR_BG = "#050507"
ACCENT = "#3b82f6"
# key, nhãn, màu nền trang (khớp với nền của từng app)
TABS = (
    ("translate", "🈶  Dịch truyện", builder.BG, "Ctrl+1"),
    ("library", "📚  Biên tập thư viện", "#0b1220", "Ctrl+2"),
)


class StoryStudio:
    def __init__(self, root):
        self.root = root
        self._resize_timer = None
        self._catalog_stamp = None
        cfg = builder.load_config()
        root.geometry(cfg.get("studio_main", "1300x780"))
        root.minsize(1040, 680)
        root.configure(bg=TAB_BAR_BG)

        self.tab_bar = tk.Frame(root, bg=TAB_BAR_BG)
        self.tab_bar.pack(fill="x")
        body = tk.Frame(root, bg=TAB_BAR_BG)
        body.pack(fill="both", expand=True)

        self.pages = {key: tk.Frame(body, bg=bg) for key, _label, bg, _key in TABS}
        # Tạo builder trước: editor cấu hình theme ttk sau cùng, nên combobox
        # trong trang Biên tập giữ đúng kiểu dáng của nó.
        self.translator = builder.TranslatorGUI(root, self.pages["translate"])
        self.editor = editor.ChapterEditorApp(root, self.pages["library"])
        self._catalog_stamp = self._catalog_mtime()

        self.tab_widgets = {}
        for key, label, _bg, shortcut in TABS:
            tab = tk.Frame(self.tab_bar, bg=TAB_BAR_BG, cursor="hand2")
            tab.pack(side="left", padx=(12 if not self.tab_widgets else 0, 0))
            text = tk.Label(tab, text=label, bg=TAB_BAR_BG, font=("Segoe UI", 10, "bold"), padx=18, pady=9)
            text.pack()
            line = tk.Frame(tab, height=3, bg=TAB_BAR_BG)
            line.pack(fill="x")
            for widget in (tab, text, line):
                widget.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.tab_widgets[key] = (tab, text, line)
            root.bind(f"<Control-Key-{len(self.tab_widgets)}>", lambda e, k=key: (self.show(k), "break")[1])
        tk.Label(self.tab_bar, text="Ctrl+1 / Ctrl+2 để chuyển tab", bg=TAB_BAR_BG, fg="#52525b",
                 font=("Segoe UI", 9)).pack(side="right", padx=16)

        self.current = None
        start = cfg.get("studio_tab", "translate")
        self.show(start if start in self.pages else "translate")

        root.bind("<Configure>", self._on_root_configure)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ── tab ──

    def show(self, key):
        if key == self.current:
            return
        if self.current:
            self.pages[self.current].pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        self.current = key
        for tab_key, label, bg, _shortcut in TABS:
            _tab, text, line = self.tab_widgets[tab_key]
            active = tab_key == key
            text.config(bg=bg if active else TAB_BAR_BG, fg="#ffffff" if active else "#71717a")
            line.config(bg=ACCENT if active else TAB_BAR_BG)
            _tab.config(bg=bg if active else TAB_BAR_BG)
            if active:
                self.root.title(f"Story Studio — {label.split(maxsplit=1)[-1]}")
        if key == "library":
            self._refresh_library()
        builder.save_config({"studio_tab": key})

    def _catalog_mtime(self):
        try:
            return os.path.getmtime(editor.CATALOG_PATH)
        except OSError:
            return None

    def _refresh_library(self):
        """Trang Dịch có thể vừa lưu truyện/chương vào thư viện: nạp lại danh mục."""
        stamp = self._catalog_mtime()
        if stamp == self._catalog_stamp:
            return
        self._catalog_stamp = stamp
        self.editor.load_story_list()
        if self.editor.story_combo.get().strip():
            # Cập nhật danh sách chương và mã chương kế tiếp của truyện đang chọn.
            self.editor.on_story_selected()

    # ── cửa sổ ──

    def _on_root_configure(self, event=None):
        if event and event.widget is not self.root:
            return
        if self._resize_timer:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(600, self._save_geometry)

    def _save_geometry(self):
        self._resize_timer = None
        builder.save_config({"studio_main": self.root.geometry()})

    def on_close(self):
        reviews = [w for w in self.root.winfo_children()
                   if isinstance(w, tk.Toplevel) and w.title().startswith("Review & Edit Name")]
        if reviews:
            reviews[0].lift()
            messagebox.showwarning("Còn cửa sổ Review",
                                   "Hãy đóng cửa sổ Review bản dịch trước để lưu hoặc giữ nháp.",
                                   parent=reviews[0])
            return
        worker = self.translator._worker
        if worker is not None and worker.is_alive():
            self.show("translate")
            if not messagebox.askyesno("Đang dịch", "Bản dịch đang chạy. Thoát và bỏ phần đang dịch?",
                                       parent=self.root, icon="warning", default="no"):
                return
            self.translator._cancel_event.set()
        if self.editor.is_dirty():
            self.show("library")
        if not self.editor.confirm_discard("thoát"):
            return
        self._save_geometry()
        self.root.destroy()


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    StoryStudio(root)
    root.mainloop()
