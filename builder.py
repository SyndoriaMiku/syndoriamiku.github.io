import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import requests, json, os, sys, base64, datetime, time, threading, queue
import unicodedata, re, shutil
from tkinterdnd2 import TkinterDnD, DND_FILES
from name_glossary import (update_name_cfg, compile_name_source_pattern, compile_name_loose_pattern,
                           substitute_names, fix_name_spacing)
import library_store as store
from library_store import CatalogError, read_catalog, write_catalog
from editor_widgets import search_key
try:
    import han_viet as _hv
    _HAN_VIET_OK = True
except ImportError:
    _HAN_VIET_OK = False

try:
    from gpu_name_scanner import NameScanner as _NameScanner
    from gpu_name_scanner import is_installed as _ner_installed, preload_in_background as _ner_preload
    _NAME_SCANNER_OK = True
except ImportError:
    _NameScanner = None
    _NAME_SCANNER_OK = False


# --- XÁC ĐỊNH THƯ MỤC GỐC ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    if os.path.basename(BASE_DIR).lower() == 'dist':
        BASE_DIR = os.path.dirname(BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- CẤU HÌNH API ---
API_URL = "https://comic.sangtacvietcdn.xyz/tsm.php?cdn=/"
TEMPLATE_FILE = os.path.join(BASE_DIR, "reader.html")
CHUNK_LIMIT = 20000
DELAY = 1.2
CONFIG_PATH = os.path.join(BASE_DIR, "editor_config.json")
STORIES_DIR = os.path.join(BASE_DIR, "stories")
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
LIBRARY_CATALOG = os.path.join(LIBRARY_DIR, "list.json")
DRAFT_DIR = os.path.join(BASE_DIR, ".drafts")

# Bảng màu dùng chung
BG, PANEL, FIELD, MUTED, TEXT = "#09090b", "#18181b", "#27272a", "#a1a1aa", "#e4e4e7"


def name_cfg_path():
    """name.cfg sits next to the exe when frozen, else next to this file."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "name.cfg")
    return os.path.join(BASE_DIR, "name.cfg")


def draft_path(slug):
    return os.path.join(DRAFT_DIR, f"{slug}.json")


def write_draft(title, slug, cn_lines, vi_lines):
    store.write_json_atomic(draft_path(slug), {
        "title": title, "slug": slug, "cn": list(cn_lines), "vi": list(vi_lines),
        "time": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
    })


def remove_draft(slug):
    try:
        os.remove(draft_path(slug))
    except OSError:
        pass


def estimate_chunks(lines, limit=CHUNK_LIMIT):
    """Same grouping rule as run_process (before name substitution)."""
    chunks, current = 0, 0
    for line in lines:
        added = len(line) + (1 if current else 0)
        if current and current + added > limit:
            chunks += 1
            current = len(line)
        else:
            current += added
    return chunks + (1 if current else 0)


def split_translation(lines, limit=CHUNK_LIMIT):
    """Group (orig, replaced) lines into API chunks of <= limit characters."""
    chunks, group, length = [], [], 0
    for orig_line, rep_line in lines:
        added = len(rep_line) + (1 if group else 0)
        if not group or length + added <= limit:
            group.append((orig_line, rep_line))
            length += added
        else:
            chunks.append(group)
            group, length = [(orig_line, rep_line)], len(rep_line)
    if group:
        chunks.append(group)
    return chunks


def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(data):
    try:
        existing = load_config()
        existing.update(data)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception:
        pass



def slugify_vn(text):
    """Convert a Vietnamese (or any) title into a URL-friendly slug."""
    _vn_map = str.maketrans("đĐ", "dD")
    text = text.translate(_vn_map)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


def compile_name_pattern(vi_names):
    names = sorted(set(n.strip() for n in vi_names if n and n.strip()), key=len, reverse=True)
    return re.compile(r'(?<!\w)(?:' + '|'.join(map(re.escape, names)) + r')(?!\w)') if names else None


def fix_capitalization_after_names(text: str, vi_names: list, name_pattern=None) -> str:
    """
    Hạ chữ hoa sai sau tên riêng hoặc ký tự ẩn giữa câu do API giữ lại.
    Không hạ chữ hoa nếu chuỗi tiếp theo là khởi đầu của một Tên riêng khác trong từ điển.
    """
    if not text:
        return text

    # Khớp tên dài trước, đúng ranh giới từ để không sửa bên trong tên khác.
    matches = []
    pattern = name_pattern if name_pattern is not None else compile_name_pattern(vi_names)
    if pattern is not None:
        matches = list(pattern.finditer(text))
    name_starts = {match.start() for match in matches}
    candidates = {}
    horizontal_space = r'[^\S\r\n\v\f\x85\u2028\u2029]'
    invisible = r'[\u200b-\u200d\u2060\ufeff]'
    separator = rf'(?:{horizontal_space}|{invisible})'
    following_pattern = re.compile(separator + r'+(\w+)')
    for match in matches:
        # API có thể giữ ký tự ẩn từ bản gốc giữa tên và từ tiếp theo
        # (đặc biệt ZWNJ U+200C). Giữ các ký tự này, chỉ sửa chữ hoa.
        # Không đi qua dấu câu hoặc xuống dòng (đầu câu mới).
        following = following_pattern.match(text, match.end())
        if not following:
            continue
        start = following.start(1)
        word = following.group(1)
        candidates[start] = word

    # Một tên có thể được API dịch khác config ("mây thư"), hoặc không có
    # trong config. Ký tự ẩn vẫn có thể làm API viết hoa nhầm từ tiếp theo.
    # Yêu cầu trước khoảng phân cách là một ký tự từ: không vượt qua dấu
    # kết câu, dấu mở lời thoại hay xuống dòng.
    hidden_boundary = re.compile(rf'(?<=\w){horizontal_space}*{invisible}{separator}*(\w+)')
    for match in hidden_boundary.finditer(text):
        candidates[match.start(1)] = match.group(1)

    edits = []
    for start, word in sorted(candidates.items()):
        if start in name_starts:
            continue
        # Giữ nguyên từ viết tắt như VIP, FBI.
        if word.istitle() and not (word.isupper() and len(word) > 1):
            edits.append((start, start + len(word), word.lower()))

    parts = []
    cursor = 0
    for start, end, replacement in edits:
        parts.extend((text[cursor:start], replacement))
        cursor = end
    parts.append(text[cursor:])
    return ''.join(parts)


def prepare_name_updates(vi_lines, wrong, right, vi_names):
    """Compute changed lines only; safe to run without accessing Tk widgets."""
    if not wrong:
        return []
    wrong_pattern = re.compile(re.escape(wrong), re.IGNORECASE)
    name_pattern = compile_name_pattern(vi_names)
    spacing_pattern = compile_name_loose_pattern([right])
    updates = []
    for index, original in enumerate(vi_lines):
        if not wrong_pattern.search(original):
            continue
        translated = wrong_pattern.sub(lambda match: right, original)
        translated = unicodedata.normalize('NFC', translated)
        translated = fix_name_spacing(translated, spacing_pattern)
        translated = fix_capitalization_after_names(translated, vi_names, name_pattern)
        if translated != original:
            updates.append((index, translated))
    return updates


# --- CỬA SỔ REVIEW ---
class ReviewWindow:
    def __init__(self, parent, title, slug, cn_lines, vi_lines, app_instance, from_draft=False):
        self.top = tk.Toplevel(parent)
        self.top.title(f"Review & Edit Name: {title}")
        self.top.configure(bg=BG)

        self.title = title
        self.slug = slug
        self.cn_lines = cn_lines
        self.vi_lines = vi_lines
        self.app = app_instance
        self.saved = False            # đã lưu data.json hoặc vào thư viện
        self._saved_data_once = False  # đã ghi stories/<slug>/data.json trong phiên này
        self._draft_timer = None
        self._status_timer = None

        # Restore saved geometry or use default
        cfg = load_config()
        geo = cfg.get("builder_review", "900x700")
        self.top.geometry(geo)

        self.top.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.setup_ui()
        self.load_content()
        if from_draft:
            self.set_status(f"📝 Đã mở nháp: {len(cn_lines)} đoạn — chưa lưu", "#f59e0b")
        else:
            self.save_draft()

    # ── nháp & trạng thái ──

    def set_status(self, text, color="#10b981"):
        self.status_lbl.config(text=text, fg=color)

    def mark_changed(self):
        self.saved = False
        if self._draft_timer:
            self.top.after_cancel(self._draft_timer)
        self._draft_timer = self.top.after(1500, self.save_draft)

    def save_draft(self):
        self._draft_timer = None
        try:
            write_draft(self.title, self.slug, self.cn_lines, self.vi_lines)
            self.set_status(f"📝 Nháp tự lưu lúc {time.strftime('%H:%M:%S')} — .drafts/{self.slug}.json",
                            "#71717a" if self.saved else "#f59e0b")
        except Exception as error:
            self.set_status(f"⚠ Không lưu được nháp: {error}", "#ef4444")

    def _release_app(self):
        self.app.btn_run.config(state="normal")
        self.app.set_status("Sẵn sàng", "#71717a")
        self.app.btn_clear.pack(side="right", padx=5)

    def close_window(self):
        if self._draft_timer:
            self.top.after_cancel(self._draft_timer)
            self._draft_timer = None
        save_config({"builder_review": self.top.geometry()})
        if self.saved:
            remove_draft(self.slug)
        else:
            self.save_draft()
        self.top.destroy()

    def on_closing(self):
        if not self.saved:
            answer = messagebox.askyesnocancel(
                "Bản dịch chưa lưu",
                "Bản dịch này chưa được lưu.\n\n"
                "Có = Lưu vào data.json rồi đóng\n"
                "Không = Đóng (nháp vẫn giữ, mở lại bằng nút \"Mở nháp\")\n"
                "Hủy = Quay lại",
                parent=self.top, icon="warning")
            if answer is None:
                return
            if answer:
                self.save_data()
                return
        self._release_app()
        self.close_window()

    def setup_ui(self):
        ctrl_frame = tk.Frame(self.top, bg=BG)
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        tk.Label(ctrl_frame, text="Bôi đen ➡️ chuột phải: Thêm Name  ·  Bấm đúp một dòng để sửa câu",
                 fg=MUTED, bg=BG).pack(side="left")

        btn = dict(fg="white", borderwidth=0, padx=12, cursor="hand2")
        tk.Button(ctrl_frame, text="💾 Lưu data.json", command=self.save_data, bg="#10b981", **btn).pack(side="right")
        tk.Button(ctrl_frame, text="📚 Lưu vào thư viện", command=self.save_to_library, bg="#0f766e", **btn).pack(side="right", padx=(0, 10))
        tk.Button(ctrl_frame, text="✏️ Thêm Name", command=self.prompt_add_name, bg="#3b82f6", **btn).pack(side="right", padx=(0, 10))
        tk.Button(ctrl_frame, text="🔄 Dịch Lại Toàn Bộ", command=self.retranslate_all, bg="#f59e0b", **btn).pack(side="right", padx=(0, 10))
        tk.Button(ctrl_frame, text="🔍 Kiểm tra lỗi", command=self.check_translation_errors, bg="#ef4444", **btn).pack(side="right", padx=(0, 10))

        self.status_lbl = tk.Label(self.top, text="", fg="#71717a", bg=BG, anchor="w", font=("Arial", 9))
        self.status_lbl.pack(side="bottom", fill="x", padx=12, pady=(0, 6))

        self.text_editor = scrolledtext.ScrolledText(self.top, wrap=tk.WORD, bg=PANEL, fg=TEXT, font=("Consolas", 11), borderwidth=0)
        self.text_editor.pack(fill="both", expand=True, padx=10, pady=5)

        self.text_editor.tag_config("cn", foreground="#71717a")
        self.text_editor.tag_config("vi", foreground="#ffffff")
        self.text_editor.tag_config("line_hover", background="#1f2937")

        self.menu = tk.Menu(self.top, tearoff=0, bg=FIELD, fg="white", borderwidth=0)
        self.menu.add_command(label="Sửa lỗi & Thêm Name (từ đoạn bôi đen)", command=self.prompt_add_name)
        self.menu.add_command(label="Sửa câu dịch của đoạn này", command=lambda: self.edit_line(self._menu_index))
        self._menu_index = None

        self.text_editor.bind("<Button-3>", self.show_context_menu)
        self.text_editor.bind("<Double-Button-1>", self._on_double_click)
        self.top.bind("<Control-s>", lambda e: (self.save_data(), "break")[1])

    # ── ánh xạ dòng Text <-> đoạn ──

    def _pair_index_at(self, index):
        line = int(self.text_editor.index(index).split(".")[0])
        pair, offset = divmod(line - 1, 3)
        if offset in (0, 1) and 0 <= pair < len(self.vi_lines):
            return pair
        return None

    def _on_double_click(self, event):
        pair = self._pair_index_at(f"@{event.x},{event.y}")
        if pair is not None:
            self.edit_line(pair)
        return "break"

    def retranslate_all(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn dịch lại toàn bộ truyện không? (Sẽ tốn thời gian gọi API từ đầu)", parent=self.top):
            self.app.btn_run.config(state="normal")
            self.close_window()
            self.app.start_thread()

    def check_translation_errors(self):
        self.text_editor.tag_remove("error_highlight", "1.0", tk.END)
        self.text_editor.tag_config("error_highlight", background="#ef4444", foreground="white")

        # Ký tự Hán chưa dịch, ký tự lỗi Unicode � và dòng API lỗi
        error_pattern = re.compile(r'[㐀-䶿一-鿿�]|\[Lỗi dịch\]')
        error_count = 0

        self.text_editor.config(state=tk.NORMAL)
        for i, text in enumerate(self.vi_lines):
            line_idx = i * 3 + 2
            for match in error_pattern.finditer(text):
                start, end = match.span()
                self.text_editor.tag_add("error_highlight", f"{line_idx}.{start}", f"{line_idx}.{end}")
                error_count += 1
        self.text_editor.config(state=tk.DISABLED)

        if error_count > 0:
            messagebox.showwarning("Phát hiện lỗi", f"Tìm thấy {error_count} chỗ chưa dịch, lỗi font () hoặc [Lỗi dịch].\nĐã bôi đỏ các chỗ này — bấm đúp dòng để sửa.", parent=self.top)
            first_error = self.text_editor.tag_ranges("error_highlight")
            if first_error:
                self.text_editor.see(first_error[0])
        else:
            messagebox.showinfo("Hoàn tất", "Không phát hiện ký tự tiếng Trung chưa dịch hay lỗi font.", parent=self.top)

    def load_content(self):
        # Lưu lại vị trí cuộn chuột (scrollbar) và con trỏ hiện tại
        scroll_pos = self.text_editor.yview()
        insert_pos = self.text_editor.index("insert")

        self.text_editor.config(state=tk.NORMAL)
        self.text_editor.delete(1.0, tk.END)
        for i in range(len(self.cn_lines)):
            self.text_editor.insert(tk.END, f"{self.cn_lines[i]}\n", "cn")
            self.text_editor.insert(tk.END, f"{self.vi_lines[i]}\n\n", "vi")
        self.text_editor.config(state=tk.DISABLED)

        self.text_editor.update_idletasks()
        self.text_editor.mark_set("insert", insert_pos)
        self.text_editor.yview_moveto(scroll_pos[0])
        self.text_editor.after(10, lambda: self.text_editor.yview_moveto(scroll_pos[0]))
        self.text_editor.after(50, lambda: self.text_editor.yview_moveto(scroll_pos[0]))
        self.text_editor.after(100, lambda: self.text_editor.yview_moveto(scroll_pos[0]))

    def show_context_menu(self, event):
        self._menu_index = self._pair_index_at(f"@{event.x},{event.y}")
        try:
            self.text_editor.get(tk.SEL_FIRST, tk.SEL_LAST)
            has_selection = True
        except tk.TclError:
            has_selection = False
        self.menu.entryconfig(0, state="normal" if has_selection else "disabled")
        self.menu.entryconfig(1, state="normal" if self._menu_index is not None else "disabled")
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    # ── sửa trực tiếp một câu ──

    def edit_line(self, index):
        if index is None or not 0 <= index < len(self.vi_lines):
            return
        dialog = tk.Toplevel(self.top)
        dialog.title(f"Sửa đoạn {index + 1}/{len(self.vi_lines)}")
        dialog.configure(bg=PANEL)
        dialog.transient(self.top)
        geo = load_config().get("builder_edit_line", "760x360")
        try:
            dialog.geometry(geo)
        except tk.TclError:
            dialog.geometry("760x360")

        tk.Label(dialog, text="Tiếng Trung gốc:", fg=MUTED, bg=PANEL).pack(anchor="w", padx=14, pady=(10, 2))
        cn_box = tk.Text(dialog, height=3, wrap=tk.WORD, bg=BG, fg="#a1a1aa", font=("Consolas", 11),
                         borderwidth=0, padx=8, pady=6)
        cn_box.insert("1.0", self.cn_lines[index])
        cn_box.config(state=tk.DISABLED)
        cn_box.pack(fill="x", padx=14)

        tk.Label(dialog, text="Bản dịch (Ctrl+Enter để lưu, Esc để hủy):", fg="#10b981", bg=PANEL,
                 font=("Arial", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        vi_box = tk.Text(dialog, height=6, wrap=tk.WORD, bg=FIELD, fg="white", insertbackground="white",
                         font=("Consolas", 11), borderwidth=0, padx=8, pady=6, undo=True)
        vi_box.insert("1.0", self.vi_lines[index])
        vi_box.pack(fill="both", expand=True, padx=14)
        vi_box.focus_set()
        vi_box.mark_set("insert", "end-1c")

        def close(event=None):
            save_config({"builder_edit_line": dialog.geometry()})
            dialog.destroy()
            return "break"

        def apply(event=None):
            # Mỗi đoạn phải nằm trên một dòng để giữ cặp Trung/Việt.
            new_text = " ".join(vi_box.get("1.0", "end-1c").split())
            new_text = unicodedata.normalize('NFC', new_text)
            if new_text != self.vi_lines[index]:
                line = index * 3 + 2
                self.text_editor.config(state=tk.NORMAL)
                self.text_editor.replace(f"{line}.0", f"{line}.end", new_text, "vi")
                self.text_editor.config(state=tk.DISABLED)
                self.vi_lines[index] = new_text
                self.mark_changed()
            return close()

        buttons = tk.Frame(dialog, bg=PANEL)
        buttons.pack(fill="x", padx=14, pady=10)
        tk.Button(buttons, text="Hủy", command=close, bg=FIELD, fg="white", borderwidth=0, padx=14).pack(side="right")
        tk.Button(buttons, text="💾 Lưu câu", command=apply, bg="#10b981", fg="white", borderwidth=0, padx=14).pack(side="right", padx=8)
        vi_box.bind("<Control-Return>", apply)
        dialog.bind("<Escape>", close)
        dialog.protocol("WM_DELETE_WINDOW", close)

    # ── thêm / sửa name ──

    def prompt_add_name(self):
        try:
            selected_text = self.text_editor.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            selected_text = ""

        # Check xem chuỗi bôi đen có chứa ký tự CJK (Tiếng Trung) không
        is_cn = any('一' <= char <= '鿿' for char in selected_text)

        dialog = tk.Toplevel(self.top)
        dialog.title("Sửa lỗi & Thêm Name Mới")
        dialog.configure(bg=PANEL)
        dialog.transient(self.top)
        dialog.grab_set()

        _cfg = load_config()
        _geo = _cfg.get("builder_add_name", "420x350")
        try:
            dialog.geometry(_geo)
        except Exception:
            dialog.geometry("420x350")
        dialog.resizable(True, True)

        entry_opts = dict(bg=FIELD, fg="white", borderwidth=0, insertbackground="white")
        tk.Label(dialog, text="1. Tiếng Trung gốc (để lưu Name dùng vĩnh viễn):", fg=MUTED, bg=PANEL).pack(pady=(10,0), anchor="w", padx=20)
        ent_cn = tk.Entry(dialog, **entry_opts)
        ent_cn.pack(fill="x", padx=20, pady=5, ipady=5)
        if is_cn and selected_text:
            ent_cn.insert(0, selected_text)

        tk.Label(dialog, text="2. Cụm từ VN bị dịch sai (để thay thế trong bài này):", fg=MUTED, bg=PANEL).pack(pady=(10,0), anchor="w", padx=20)
        ent_wrong = tk.Entry(dialog, **entry_opts)
        ent_wrong.pack(fill="x", padx=20, pady=5, ipady=5)
        if not is_cn and selected_text:
            ent_wrong.insert(0, selected_text)

        tk.Label(dialog, text="3. Sửa thành (Name đúng):", fg="#10b981", bg=PANEL, font=("Arial", 10, "bold")).pack(pady=(10,0), anchor="w", padx=20)
        ent_right = tk.Entry(dialog, **entry_opts)
        ent_right.pack(fill="x", padx=20, pady=5, ipady=5)
        ent_right.focus_set()

        if is_cn and selected_text:
            # Gợi ý Name bằng API dịch; cập nhật ô qua hàng đợi luồng chính.
            def fetch_suggestion(cn_text):
                try:
                    res = self.app.translate_api(cn_text)
                except Exception:
                    return
                suggestion = res.strip().title() if res else ""
                if suggestion:
                    def safe_insert():
                        if ent_right.winfo_exists() and not ent_right.get():
                            ent_right.insert(0, suggestion)
                    self.app.call_ui(safe_insert)
            threading.Thread(target=fetch_suggestion, args=(selected_text,), daemon=True).start()

        def close_dialog(event=None):
            save_config({"builder_add_name": dialog.geometry()})
            dialog.destroy()

        def apply_name(retranslate=False):
            cn_val = unicodedata.normalize('NFC', ent_cn.get().strip())
            wrong_val = unicodedata.normalize('NFC', ent_wrong.get().strip())
            right_val = unicodedata.normalize('NFC', ent_right.get().strip())

            if not right_val:
                messagebox.showwarning("Chú ý", "Vui lòng nhập 'Name đúng'!", parent=dialog)
                return

            if retranslate:
                if not cn_val:
                    messagebox.showwarning("Chú ý", "Để dịch lại từ đầu, bắt buộc phải có 'Tiếng Trung gốc'!", parent=dialog)
                    return
                if not self.app._add_name_to_cfg(cn_val, right_val, parent=dialog):
                    return
                self.app.btn_run.config(state="normal")
                close_dialog()
                self.close_window()
                self.app.start_thread()
                return

            if not wrong_val and not cn_val:
                messagebox.showwarning("Chú ý", "Vui lòng nhập ít nhất 'Tiếng Trung' hoặc 'Từ sai'!", parent=dialog)
                return

            def set_busy(busy):
                for widget in (ent_cn, ent_wrong, ent_right, *btn_frame.winfo_children()):
                    widget.config(state="disabled" if busy else "normal")
                dialog.title("Đang cập nhật Name..." if busy else "Sửa lỗi & Thêm Name Mới")

            set_busy(True)
            vi_names = list(self.app.load_name_config().values()) + [right_val]
            snapshot = tuple(self.vi_lines)
            results = queue.Queue()

            def compute():
                try:
                    wrong = wrong_val
                    if not wrong and cn_val:
                        try:
                            auto_vi = self.app.translate_api(cn_val)
                            if auto_vi:
                                wrong = unicodedata.normalize('NFC', auto_vi.strip())
                        except Exception:
                            pass
                    updates = prepare_name_updates(snapshot, wrong, right_val, vi_names)
                    results.put((wrong, updates, None))
                except Exception as error:
                    results.put(('', [], str(error)))

            def finish(count):
                if cn_val:
                    self.app._add_name_to_cfg(cn_val, right_val, parent=self.top)
                close_dialog()
                if count:
                    self.mark_changed()
                self.set_status(f"✅ {cn_val or wrong_val} → {right_val}: đã sửa {count} đoạn"
                                + (" · đã lưu vào name.cfg" if cn_val else ""))

            def poll():
                try:
                    wrong, updates, error = results.get_nowait()
                except queue.Empty:
                    dialog.after(25, poll)
                    return
                if error:
                    set_busy(False)
                    messagebox.showerror("Lỗi cập nhật Name", error, parent=dialog)
                    return
                if not wrong:
                    if not messagebox.askyesno("Xác nhận", "Không tìm được cụm từ VN cần thay. Chỉ lưu Name để áp dụng cho những lần dịch sau?", parent=dialog):
                        set_busy(False)
                        return
                # Prevent closing midway through a multi-batch UI update.
                dialog.protocol("WM_DELETE_WINDOW", lambda: None)
                self.apply_name_updates(updates, lambda: finish(len(updates)))

            threading.Thread(target=compute, daemon=True).start()
            dialog.after(25, poll)

        btn_frame = tk.Frame(dialog, bg=PANEL)
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="🚀 Cập nhật nhanh (Enter)", command=lambda: apply_name(False), bg="#3b82f6", fg="white", borderwidth=0).pack(side="left", padx=10, ipadx=10, ipady=5)
        tk.Button(btn_frame, text="🔄 Dịch Lại Toàn Bộ", command=lambda: apply_name(True), bg="#f59e0b", fg="white", borderwidth=0).pack(side="left", padx=10, ipadx=10, ipady=5)
        dialog.bind("<Return>", lambda e: apply_name(False))
        dialog.bind("<Escape>", close_dialog)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def apply_name_updates(self, updates, on_done):
        """Write changed VI rows in short batches, leaving CN rows untouched."""
        pending = iter(updates)

        def paint():
            deadline = time.perf_counter() + 0.008
            complete = False
            self.text_editor.config(state=tk.NORMAL)
            try:
                while time.perf_counter() < deadline:
                    try:
                        index, translated = next(pending)
                    except StopIteration:
                        complete = True
                        break
                    line = index * 3 + 2
                    self.text_editor.replace(f"{line}.0", f"{line}.end", translated, "vi")
                    self.vi_lines[index] = translated
            finally:
                self.text_editor.config(state=tk.DISABLED)
            if complete:
                on_done()
            else:
                self.top.after(1, paint)

        paint()

    # ── lưu ──

    def save_data(self):
        output_dir = os.path.join(STORIES_DIR, self.slug)
        data_path = os.path.join(output_dir, "data.json")
        if os.path.exists(data_path) and not self._saved_data_once:
            if not messagebox.askyesno(
                    "Ghi đè truyện?",
                    f"stories/{self.slug}/data.json đã tồn tại (có thể là truyện khác trùng tên).\n\nGhi đè?",
                    parent=self.top, icon="warning", default="no"):
                return

        story_data = {"title": self.title, "content": []}
        for cn_line, vi_line in zip(self.cn_lines, self.vi_lines):
            cn_nfc = unicodedata.normalize('NFC', cn_line)
            # Loại bỏ dấu cách kép, rồi chuẩn hoá NFC lại
            vi_clean = unicodedata.normalize('NFC', re.sub(r'  +', ' ', unicodedata.normalize('NFC', vi_line)).strip())
            story_data["content"].append({"cn": store.b64(cn_nfc), "vi": store.b64(vi_clean)})

        try:
            os.makedirs(output_dir, exist_ok=True)
            store.write_json_atomic(data_path, story_data)
            if os.path.exists(TEMPLATE_FILE):
                shutil.copy2(TEMPLATE_FILE, os.path.join(output_dir, "index.html"))
            self.app.update_catalog(self.title, self.slug)
        except Exception as error:
            messagebox.showerror("Lỗi khi lưu", str(error), parent=self.top)
            return

        self._saved_data_once = True
        self.saved = True
        self.app.set_status("✅ Đã lưu data.json thành công!", "#10b981")
        self.app.btn_run.config(state="normal")
        self.app.btn_clear.pack(side="right", padx=5)
        messagebox.showinfo("Thành công", f"Đã xuất dữ liệu truyện: {self.slug}", parent=self.top)
        self.close_window()

    def save_to_library(self):
        """Lưu thẳng vào library/<truyện>/<chương> — không cần qua editor."""
        try:
            catalog = read_catalog(LIBRARY_CATALOG)
        except CatalogError as error:
            messagebox.showerror("Không đọc được danh mục thư viện", f"{error}\n\nĐã dừng để không ghi đè list.json.", parent=self.top)
            return
        options = [f'{item["slug"]} | {item.get("title", "")}' for item in
                                   sorted(catalog, key=lambda it: float(it.get("timestamp") or 0), reverse=True)
                                   if item.get("slug")]
        pairs = list(zip(self.cn_lines, self.vi_lines))
        patterns = list(store.DEFAULT_SPLIT_PATTERNS)
        for item in load_config().get("split_patterns", []):
            if isinstance(item, (list, tuple)) and len(item) == 2 and not any(item[1] == rx for _n, rx in patterns):
                patterns.append((item[0], item[1]))

        dlg = tk.Toplevel(self.top)
        dlg.title("📚 Lưu vào thư viện")
        dlg.configure(bg=PANEL)
        dlg.transient(self.top)
        dlg.grab_set()
        geo = load_config().get("builder_library_dialog", "620x560")
        try:
            dlg.geometry(geo)
        except tk.TclError:
            dlg.geometry("620x560")
        dlg.minsize(520, 480)

        label = dict(bg=PANEL, fg=MUTED, font=("Arial", 9, "bold"))
        radio = dict(bg=PANEL, fg="white", selectcolor=BG, activebackground=PANEL, activeforeground="white")
        entry = dict(bg=FIELD, fg="white", insertbackground="white", borderwidth=0)

        # 1. Truyện
        tk.Label(dlg, text="1. TRUYỆN", **label).pack(anchor="w", padx=16, pady=(12, 4))
        story_mode = tk.StringVar(value="existing" if options else "new")
        row_new = tk.Frame(dlg, bg=PANEL)
        row_new.pack(fill="x", padx=16)
        tk.Radiobutton(row_new, text="Truyện mới:", variable=story_mode, value="new", **radio).pack(side="left")
        new_title = tk.Entry(row_new, **entry)
        new_title.insert(0, self.title)
        new_title.pack(side="left", fill="x", expand=True, ipady=4, padx=(6, 0))

        row_exist = tk.Frame(dlg, bg=PANEL)
        row_exist.pack(fill="x", padx=16, pady=(6, 0))
        tk.Radiobutton(row_exist, text="Truyện có sẵn — tìm:", variable=story_mode, value="existing", **radio).pack(side="left")
        story_filter = tk.Entry(row_exist, **entry)
        story_filter.pack(side="left", fill="x", expand=True, ipady=4, padx=(6, 0))
        story_list = tk.Listbox(dlg, height=6, bg=BG, fg=TEXT, selectbackground="#0f766e", borderwidth=0,
                                highlightthickness=0, exportselection=False, activestyle="none")
        story_list.pack(fill="x", padx=16, pady=(4, 0))

        def refresh_story_list(event=None):
            words = search_key(story_filter.get()).split()
            current = story_list.get(story_list.curselection()[0]) if story_list.curselection() else None
            story_list.delete(0, tk.END)
            for option in options:
                if all(w in search_key(option) for w in words):
                    story_list.insert(tk.END, option)
            items = story_list.get(0, tk.END)
            if current in items:
                story_list.selection_set(items.index(current))
            elif items:
                story_list.selection_set(0)
            if event is not None:
                story_mode.set("existing")
            update_preview()
        story_filter.bind("<KeyRelease>", refresh_story_list)
        story_list.bind("<<ListboxSelect>>", lambda e: (story_mode.set("existing"), update_preview()))
        new_title.bind("<KeyRelease>", lambda e: (story_mode.set("new"), update_preview()))

        # 2. Chương
        tk.Label(dlg, text="2. CHIA CHƯƠNG", **label).pack(anchor="w", padx=16, pady=(14, 4))
        split_mode = tk.StringVar(value="one")
        row_one = tk.Frame(dlg, bg=PANEL)
        row_one.pack(fill="x", padx=16)
        tk.Radiobutton(row_one, text="Một chương, tên:", variable=split_mode, value="one", **radio).pack(side="left")
        one_title = tk.Entry(row_one, **entry)
        one_title.insert(0, self.title)
        one_title.pack(side="left", fill="x", expand=True, ipady=4, padx=(6, 0))

        row_split = tk.Frame(dlg, bg=PANEL)
        row_split.pack(fill="x", padx=16, pady=(6, 0))
        tk.Radiobutton(row_split, text="Tách theo mẫu:", variable=split_mode, value="split", **radio).pack(side="left")
        pattern_var = tk.StringVar(value=patterns[0][1])
        pattern_combo = ttk.Combobox(row_split, textvariable=pattern_var,
                                     values=[rx for _n, rx in patterns], font=("Consolas", 9))
        pattern_combo.pack(side="left", fill="x", expand=True, padx=(6, 0))
        pattern_hint = tk.Label(dlg, text=" · ".join(n for n, _ in patterns), fg="#52525b", bg=PANEL,
                                font=("Arial", 8), wraplength=560, justify="left")
        pattern_hint.pack(anchor="w", padx=16, pady=(2, 0))
        one_title.bind("<KeyRelease>", lambda e: (split_mode.set("one"), update_preview()))
        pattern_combo.bind("<<ComboboxSelected>>", lambda e: (split_mode.set("split"), update_preview()))
        pattern_combo.bind("<KeyRelease>", lambda e: (split_mode.set("split"), update_preview()))
        split_mode.trace_add("write", lambda *_: update_preview())
        story_mode.trace_add("write", lambda *_: update_preview())

        # 3. Xem trước
        tk.Label(dlg, text="3. XEM TRƯỚC", **label).pack(anchor="w", padx=16, pady=(14, 4))
        preview = tk.Text(dlg, height=7, bg=BG, fg="#cbd5e1", borderwidth=0, font=("Consolas", 9), padx=8, pady=6)
        preview.pack(fill="both", expand=True, padx=16)
        plan = {"slug": None, "title": None, "chapters": [], "error": None}

        def selected_story():
            if story_mode.get() == "new":
                title = new_title.get().strip()
                return (store.next_story_id(catalog), title, True) if title else (None, None, True)
            if story_list.curselection():
                slug, title = (p.strip() for p in story_list.get(story_list.curselection()[0]).split("|", 1))
                return slug, title, False
            return None, None, False

        def update_preview(*_args):
            slug, title, is_new = selected_story()
            plan.update(slug=slug, title=title, chapters=[], error=None)
            lines = []
            if not slug:
                plan["error"] = "Chọn truyện có sẵn hoặc nhập tên truyện mới."
            else:
                start = int(store.next_chapter_id(catalog, slug))
                if split_mode.get() == "one":
                    chapters = [(one_title.get().strip() or "Oneshot", pairs)]
                else:
                    try:
                        groups = store.split_into_chapters(pairs, pattern_var.get().strip() or "^$", text_of=lambda p: p[1])
                    except re.error as error:
                        groups = []
                        plan["error"] = f"Regex lỗi: {error}"
                    chapters = [(g["title"], g["items"]) for g in groups if g["items"]]
                for offset, (name, items) in enumerate(chapters):
                    chap_id = f"{start + offset:06d}"
                    name = name or f"Chương {start + offset}"
                    plan["chapters"].append((chap_id, name, items))
                    lines.append(f"{chap_id}  {name[:60]:<60}  {len(items):>4} đoạn")
                head = f"{'TRUYỆN MỚI' if is_new else 'Truyện'} {slug} | {title} — {len(plan['chapters'])} chương"
                lines.insert(0, head + "\n" + "─" * 60)
            preview.config(state=tk.NORMAL)
            preview.delete("1.0", tk.END)
            preview.insert("1.0", plan["error"] or "\n".join(lines[:300]))
            preview.config(state=tk.DISABLED)
            save_btn.config(state=tk.NORMAL if plan["chapters"] and not plan["error"] else tk.DISABLED)

        def close(event=None):
            save_config({"builder_library_dialog": dlg.geometry()})
            dlg.destroy()

        def do_save():
            slug, title = plan["slug"], plan["title"]
            if not plan["chapters"]:
                return
            try:
                fresh = read_catalog(LIBRARY_CATALOG)  # đọc lại, tránh ghi đè thay đổi từ editor
            except CatalogError as error:
                messagebox.showerror("Không đọc được danh mục", str(error), parent=dlg)
                return
            if story_mode.get() == "new":
                slug = store.next_story_id(fresh)
            clashes = [cid for cid, _n, _items in plan["chapters"]
                       if any(c.get("id") == cid for s in fresh if s.get("slug") == slug for c in s.get("chapters", []))]
            if clashes:
                messagebox.showerror("Trùng mã chương", f"Chương {', '.join(clashes[:5])} đã tồn tại. Mở lại hộp thoại để lấy mã mới.", parent=dlg)
                return
            try:
                now = datetime.datetime.now()
                store.copy_templates(LIBRARY_DIR, BASE_DIR, slug)
                for chap_id, name, items in plan["chapters"]:
                    payload = store.chapter_payload(title, name, items)
                    store.write_chapter(LIBRARY_DIR, BASE_DIR, slug, chap_id, payload)
                    store.upsert_chapter(fresh, slug, title, chap_id, name, now)
                write_catalog(LIBRARY_CATALOG, fresh)
            except Exception as error:
                messagebox.showerror("Lỗi khi lưu thư viện", str(error), parent=dlg)
                return
            self.saved = True
            first, last = plan["chapters"][0][0], plan["chapters"][-1][0]
            span = first if first == last else f"{first}–{last}"
            self.set_status(f"📚 Đã lưu {len(plan['chapters'])} chương vào library/{slug} ({span}) · {title}")
            self.app.set_status(f"📚 Đã lưu vào thư viện: {slug} | {title}", "#10b981")
            close()

        bottom = tk.Frame(dlg, bg=PANEL)
        bottom.pack(fill="x", padx=16, pady=12)
        tk.Button(bottom, text="Hủy", command=close, bg=FIELD, fg="white", borderwidth=0, padx=14, pady=4).pack(side="right")
        save_btn = tk.Button(bottom, text="📚 Lưu vào thư viện", command=do_save, bg="#0f766e", fg="white",
                             borderwidth=0, padx=14, pady=4, font=("Arial", 9, "bold"))
        save_btn.pack(side="right", padx=8)
        dlg.bind("<Escape>", close)
        dlg.protocol("WM_DELETE_WINDOW", close)
        refresh_story_list()
        story_filter.focus_set()


# --- CLASS GIAO DIỆN CHÍNH ---
class TranslatorGUI:
    def __init__(self, root, container=None):
        """``container``: khung chứa giao diện khi nhúng vào app khác (studio.py).
        Khi đó cửa sổ (tiêu đề, kích thước) do app chứa quản lý."""
        self.root = root
        self.frame = container if container is not None else root
        embedded = container is not None
        if not embedded:
            self.root.title("Story Translator Pro - SangTacViet API")
        self.frame.configure(bg=BG)
        self._resize_timer = None
        self._count_timer = None
        self._worker = None
        self._cancel_event = None
        # Luồng nền không được chạm vào Tk: mọi cập nhật giao diện đi qua hàng đợi này.
        self._ui_queue = queue.Queue()

        if not embedded:
            # Restore saved geometry or use default
            self.root.geometry(load_config().get("builder_main", "700x600"))

        self._configure_styles()
        self.setup_ui()
        self._pump_ui_queue()

        if not embedded:
            # Save geometry on resize (debounced)
            self.root.bind("<Configure>", self._on_root_configure)

        # Nạp sẵn mô hình NER đã có trên máy để lần Scan Names đầu tiên không phải chờ.
        # Tắt bằng biến môi trường STV_NER_PRELOAD=0.
        if _NAME_SCANNER_OK and os.environ.get('STV_NER_PRELOAD', '1') != '0':
            self.root.after(1500, self._preload_name_model)

    # ── luồng giao diện ──

    def call_ui(self, func, *args):
        """Thread-safe: run func(*args) on the Tk main thread."""
        self._ui_queue.put((func, args))

    def _pump_ui_queue(self):
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception as error:  # never kill the pump
                    print(f"UI callback error: {error}")
        except queue.Empty:
            pass
        self.root.after(40, self._pump_ui_queue)

    def set_status(self, text, color=None):
        """Main-thread only; background threads use call_ui(self.set_status, ...)."""
        if color:
            self.lbl_status.config(text=text, fg=color)
        else:
            self.lbl_status.config(text=text)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground="white",
                        arrowcolor=MUTED, bordercolor="#3f3f46", lightcolor="#3f3f46", darkcolor="#3f3f46")
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", "white")])
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", "white")
        style.configure("Run.Horizontal.TProgressbar", troughcolor=PANEL, background="#3b82f6",
                        bordercolor=BG, lightcolor="#3b82f6", darkcolor="#3b82f6", thickness=8)
        style.configure("Scan.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                        rowheight=26, borderwidth=0, font=("Segoe UI", 10))
        style.map("Scan.Treeview", background=[("selected", "#4c1d95")], foreground=[("selected", "white")])
        style.configure("Scan.Treeview.Heading", background=FIELD, foreground=MUTED, relief="flat",
                        font=("Arial", 8, "bold"), bordercolor=BG, lightcolor=FIELD, darkcolor=FIELD)
        style.map("Scan.Treeview.Heading", background=[("active", "#3f3f46")])
        style.configure("Vertical.TScrollbar", background="#3f3f46", troughcolor=BG, bordercolor=BG,
                        arrowcolor=MUTED, lightcolor="#3f3f46", darkcolor="#3f3f46")

    def _preload_name_model(self):
        try:
            if _ner_installed():  # chỉ nạp từ ổ đĩa, không tự tải khi khởi động
                _ner_preload()
        except Exception:
            pass  # lỗi (nếu có) sẽ hiện khi bấm Scan Names

    def _on_root_configure(self, event=None):
        if event and event.widget is not self.root:
            return
        if self._resize_timer:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(600, self._save_root_geometry)

    def _save_root_geometry(self):
        save_config({"builder_main": self.root.geometry()})

    def setup_ui(self):
        # Header
        tk.Label(self.frame, text="DỊCH TRUYỆN TRUNG - VIỆT", font=("Arial", 14, "bold"), fg="#ffffff", bg=BG).pack(pady=10)

        # Story Title Input
        frame_title = tk.Frame(self.frame, bg=BG)
        frame_title.pack(fill="x", padx=20, pady=5)
        tk.Label(frame_title, text="Story Title:", fg=MUTED, bg=BG).pack(side="left")
        self.ent_title = tk.Entry(frame_title, bg=PANEL, fg="#ffffff", insertbackground="white", borderwidth=0)
        self.ent_title.pack(side="left", fill="x", expand=True, padx=10, ipady=5)

        # Text Area for Copy-Paste
        head = tk.Frame(self.frame, bg=BG)
        head.pack(fill="x", padx=20, pady=(10, 0))
        tk.Label(head, text="Nội dung tiếng Trung:", fg=MUTED, bg=BG).pack(side="left")
        self.lbl_counter = tk.Label(head, text="", fg="#71717a", bg=BG, font=("Arial", 9))
        self.lbl_counter.pack(side="right")
        self.txt_area = scrolledtext.ScrolledText(self.frame, height=15, bg=PANEL, fg=TEXT, borderwidth=0,
                                                  font=("Consolas", 10), insertbackground="white", undo=True)
        self.txt_area.pack(fill="both", expand=True, padx=20, pady=5)
        self.txt_area.bind("<<Modified>>", self._on_text_modified)
        self.txt_area.bind("<Control-Return>", lambda e: (self.start_thread(), "break")[1])

        # Drop Zone
        self.drop_zone = tk.Label(
            self.frame, text="📂  Kéo thả file .txt vào đây",
            bg=PANEL, fg="#71717a", font=("Arial", 10),
            relief="groove", borderwidth=2, pady=12
        )
        self.drop_zone.pack(fill="x", padx=20, pady=(0, 5))
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.handle_drop)
        self.drop_zone.dnd_bind("<<DragEnter>>", lambda e: self.drop_zone.config(bg=FIELD, fg="#3b82f6"))
        self.drop_zone.dnd_bind("<<DragLeave>>", lambda e: self.drop_zone.config(bg=PANEL, fg="#71717a"))

        # Buttons Frame
        btn_frame = tk.Frame(self.frame, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=10)

        self.btn_file = tk.Button(btn_frame, text="📁 Chọn File .txt", command=self.load_file, bg=FIELD, fg="white", borderwidth=0, padx=15)
        self.btn_file.pack(side="left", padx=5)

        self.btn_scan = tk.Button(btn_frame, text="🔍 Scan Names", command=self.open_scan_names_dialog, bg="#7c3aed", fg="white", borderwidth=0, padx=15)
        self.btn_scan.pack(side="left", padx=5)

        self.btn_draft = tk.Button(btn_frame, text="📝 Mở nháp", command=self.open_draft, bg=FIELD, fg="white", borderwidth=0, padx=15)
        self.btn_draft.pack(side="left", padx=5)

        self.btn_run = tk.Button(btn_frame, text="🚀 Bắt đầu dịch", command=self.start_thread, bg="#1d4ed8", fg="white", borderwidth=0, padx=25)
        self.btn_run.pack(side="right", padx=5)

        self.btn_cancel = tk.Button(btn_frame, text="⏹ Huỷ", command=self.cancel_translation, bg="#b91c1c", fg="white", borderwidth=0, padx=15)

        self.btn_clear = tk.Button(btn_frame, text="🗑️ Xóa tất cả", command=self.clear_all, bg="#dc2626", fg="white", borderwidth=0, padx=15)

        # Progress
        self.progress = ttk.Progressbar(self.frame, style="Run.Horizontal.TProgressbar", mode="determinate")
        self.lbl_status = tk.Label(self.frame, text="Sẵn sàng  ·  Ctrl+Enter để dịch", fg="#71717a", bg=BG)
        self.lbl_status.pack(pady=5)

    # ── bộ đếm ──

    def _on_text_modified(self, event=None):
        if self.txt_area.edit_modified():
            self.txt_area.edit_modified(False)
            if self._count_timer:
                self.root.after_cancel(self._count_timer)
            self._count_timer = self.root.after(400, self.update_counter)

    def update_counter(self):
        self._count_timer = None
        content = self.txt_area.get("1.0", "end-1c")
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if not lines:
            self.lbl_counter.config(text="")
            return
        chars = sum(len(l) for l in lines)
        chunks = estimate_chunks(lines)
        # ~ 1 lần gọi API mỗi đợt + DELAY; con số chỉ để ước lượng.
        seconds = chunks * (DELAY + 4)
        eta = f"~{seconds // 60:.0f} phút" if seconds >= 90 else f"~{seconds:.0f} giây"
        self.lbl_counter.config(text=f"{chars:,} ký tự · {len(lines):,} đoạn · {chunks} đợt API · {eta}".replace(",", "."))

    def clear_all(self):
        self.ent_title.delete(0, tk.END)
        self.txt_area.delete(1.0, tk.END)
        self.set_status("Sẵn sàng", "#71717a")
        self.btn_clear.pack_forget()

    def handle_drop(self, event):
        self.drop_zone.config(bg=PANEL, fg="#71717a")
        try:
            paths = self.root.tk.splitlist(event.data)
        except tk.TclError:
            paths = [event.data.strip("{}")]
        txt_files = [p for p in paths if p.lower().endswith(".txt")]
        if not txt_files:
            messagebox.showwarning("Chú ý", "Chỉ hỗ trợ file .txt!")
            return
        self._load_from_path(txt_files[0])
        if len(txt_files) > 1:
            self.set_status(f"Đã tải {os.path.basename(txt_files[0])} (bỏ qua {len(txt_files) - 1} file còn lại)", "#f59e0b")

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self._load_from_path(file_path)

    def _load_from_path(self, file_path):
        try:
            text, encoding = store.read_text_file(file_path)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file:\n{e}")
            return
        self.txt_area.delete(1.0, tk.END)
        self.txt_area.insert(tk.END, text)

        title_suggest = os.path.splitext(os.path.basename(file_path))[0]
        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, title_suggest)
        color = "#f59e0b" if "lỗi" in encoding else "#10b981"
        self.set_status(f"Đã tải: {os.path.basename(file_path)}  ·  mã hoá {encoding}", color)
        self.update_counter()

    def open_draft(self):
        os.makedirs(DRAFT_DIR, exist_ok=True)
        path = filedialog.askopenfilename(title="Mở bản nháp", initialdir=DRAFT_DIR,
                                          filetypes=[("Bản nháp", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                draft = json.load(f)
            cn, vi = draft["cn"], draft["vi"]
            if len(cn) != len(vi):
                raise ValueError("số đoạn Trung/Việt không khớp")
        except Exception as error:
            messagebox.showerror("Lỗi", f"Không mở được nháp:\n{error}")
            return
        title = draft.get("title") or os.path.splitext(os.path.basename(path))[0]
        slug = draft.get("slug") or slugify_vn(title)
        self.btn_run.config(state="disabled")
        self.btn_clear.pack_forget()
        self.set_status(f"Đang xem nháp: {title} ({draft.get('time', '')})", "#f59e0b")
        ReviewWindow(self.root, title, slug, cn, vi, self, from_draft=True)

    def update_catalog(self, title, slug):
        catalog_path = os.path.join(STORIES_DIR, "list.json")
        os.makedirs(STORIES_DIR, exist_ok=True)
        catalog = read_catalog(catalog_path)  # lỗi đọc -> CatalogError, không ghi đè
        existing = next((item for item in catalog if item.get('slug') == slug), None)
        now = datetime.datetime.now()
        if not existing:
            catalog.append({"title": title, "slug": slug, "date": now.strftime("%d/%m/%Y"), "timestamp": now.timestamp()})
        else:
            existing['date'] = now.strftime("%d/%m/%Y")
            existing['timestamp'] = now.timestamp()
        write_catalog(catalog_path, catalog)

    def load_name_config(self):
        cfg_path = name_cfg_path()
        if not os.path.exists(cfg_path):
            try:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write("# Thêm tên cần dịch cố định vào đây theo định dạng Trung=Việt, ví dụ:\n")
                    f.write("# 轩辕=Hiên Viên\n")
            except Exception as e:
                print(f"Lỗi khi tạo file name.cfg: {e}")

        name_dict = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            cn, vi = line.split("=", 1)
                            if cn.strip() and vi.strip():
                                name_dict[unicodedata.normalize('NFC', cn.strip())] = unicodedata.normalize('NFC', vi.strip())
            except Exception as e:
                print(f"Lỗi khi đọc file name.cfg: {e}")
        return name_dict

    def translate_api(self, text):
        headers = {"Origin": "https://www.bilibili.com", "Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"}
        try:
            res = requests.post(API_URL, data={"sajax": "trans", "content": text}, headers=headers, timeout=45)
            if res.status_code == 200:
                # Normalize NFC ngay khi nhận response để đảm bảo ký tự tiếng Việt đúng chuẩn
                return unicodedata.normalize('NFC', res.text.strip())
            return None
        except Exception:
            return None

    def translate_lines(self, lines, cancel=None):
        """Keep each translated paragraph paired with its original input line (worker thread)."""
        if not lines:
            return []
        cancelled = (lambda: cancel is not None and cancel.is_set())
        translate = self.translate_api
        result = translate("\n".join(lines))
        if not result and not cancelled():
            time.sleep(3)
            result = translate("\n".join(lines))
        if not result:
            return ["[Lỗi dịch]"] * len(lines)

        translated = result.splitlines()
        if len(translated) == len(lines):
            return translated
        if len(lines) == 1:
            # Multiple output lines still belong to the same source paragraph.
            return [" ".join(translated)]

        # Never truncate extra lines or silently shift the CN/VI pairing.
        aligned = []
        for i, line in enumerate(lines):
            if cancelled():
                aligned.extend(["[Lỗi dịch]"] * (len(lines) - i))
                break
            self.call_ui(self.set_status, f"API trả lệch số dòng — đang dịch riêng {i + 1}/{len(lines)}...")
            time.sleep(DELAY)
            reply = translate(line)
            if not reply:
                time.sleep(3)
                reply = translate(line)
            aligned.append(" ".join(reply.splitlines()) if reply else "[Lỗi dịch]")
        return aligned

    # ─────────────────────────────────────────────────────────────
    # SCAN NAMES FEATURE
    # ─────────────────────────────────────────────────────────────

    def _is_cjk(self, ch: str) -> bool:
        return '\u4e00' <= ch <= '\u9fff'

    def _suggest_vi(self, cn: str) -> str:
        """Best-effort Hán-Việt suggestion: table lookup → fallback raw."""
        if _HAN_VIET_OK:
            return _hv.han_viet_name(cn)
        # Minimal inline fallback (empty if no table)
        return cn

    def scan_name_candidates(self, text: str, max_results: int = 250, on_progress=None) -> list:
        """Recognize Chinese entities locally with CUDA/CPU NER."""
        if not _NAME_SCANNER_OK:
            raise RuntimeError("Không tải được gpu_name_scanner.py. Xem SCAN_NAMES.md để cài đặt.")
        results = _NameScanner().scan(
            text, existing_glossary=set(self.load_name_config()), max_results=max_results, on_progress=on_progress,
        )
        # The legacy API provides a normal Vietnamese translation, filled below
        # after all candidates have been collected into one request.
        for item in results:
            item['suggested_vi'] = ''
        return results

    def _fill_name_suggestions_from_api(self, candidates):
        from name_suggestions import NameSuggestions
        if not hasattr(self, '_name_suggestions'):
            self._name_suggestions = NameSuggestions()

        def fetch(names):
            reply = self.translate_api('\n'.join(names))
            if not reply:
                raise RuntimeError('API dịch thường không trả kết quả.')
            return reply.splitlines()

        self._name_suggestions.fill(candidates, fetch, ('legacy', API_URL))
        return candidates

    def open_scan_names_dialog(self):
        """Open the Scan Names dialog."""
        raw_text = self.txt_area.get(1.0, tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Chú ý", "Vui lòng nhập nội dung tiếng Trung trước!")
            return

        self.root.config(cursor="watch")
        self.btn_scan.config(state="disabled", text="⏳ Đang quét...")
        self.root.update_idletasks()

        results = queue.Queue()
        def worker():
            try:
                candidates = self.scan_name_candidates(
                    raw_text, on_progress=lambda msg: results.put((None, msg, "progress")))
                api_warning = None
                try:
                    candidates = self._fill_name_suggestions_from_api(candidates)
                except Exception as error:
                    api_warning = str(error)
                results.put((candidates, api_warning, None))
            except Exception as error:
                results.put((None, None, error))

        def poll():
            try:
                candidates, api_warning, error = results.get_nowait()
            except queue.Empty:
                self.root.after(50, poll)
                return
            if error == "progress":
                self.set_status(api_warning)
                self.root.after(50, poll)
                return
            self.root.config(cursor="")
            self.btn_scan.config(state="normal", text="🔍 Scan Names")
            if error:
                messagebox.showerror("Lỗi", f"Lỗi khi quét tên:\n{error}")
                return
            self.set_status(f"Đã quét xong: tìm thấy {len(candidates)} ứng viên")
            if api_warning:
                messagebox.showwarning(
                    "Không tự dịch được tên",
                    f"Bạn vẫn có thể dùng nút Copy Hán để tra bên ngoài.\n\n{api_warning}",
                    parent=self.root,
                )
            self._show_scan_names_dialog(candidates)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(50, poll)

    def _show_scan_names_dialog(self, candidates):
        """Scan Names: bảng Treeview + khung chi tiết (nhanh với hàng trăm ứng viên)."""
        dlg = tk.Toplevel(self.root)
        dlg.title("🔍 Scan Names — Danh sách tên phát hiện")
        dlg.configure(bg=BG)
        dlg.transient(self.root)
        dlg.resizable(True, True)

        cfg = load_config()
        dlg.geometry(cfg.get("builder_scan_names", "900x640"))
        dlg.minsize(760, 520)
        filter_after_id = None

        def on_close(event=None):
            nonlocal filter_after_id
            if filter_after_id is not None:
                dlg.after_cancel(filter_after_id)
                filter_after_id = None
            save_config({"builder_scan_names": dlg.geometry()})
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", on_close)

        # Header
        hdr = tk.Frame(dlg, bg=PANEL, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔍 Scan Names", fg="#ffffff", bg=PANEL, font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=16)
        hdr_count_lbl = tk.Label(hdr, text=f"{len(candidates)} ứng viên tìm được", fg=MUTED, bg=PANEL, font=("Arial", 9))
        hdr_count_lbl.pack(side=tk.LEFT)

        def rerun():
            on_close()
            self.open_scan_names_dialog()

        tk.Button(hdr, text="🔄 Quét lại", bg="#3f3f46", fg="#ffffff", relief="flat", borderwidth=0,
                  padx=10, pady=4, font=("Arial", 8), cursor="hand2", command=rerun).pack(side=tk.RIGHT, padx=16)

        if not candidates:
            tk.Label(dlg, text="Không tìm thấy tên nào mới trong văn bản.\n(Tất cả các tên có thể đã có trong name.cfg).",
                     fg="#ef4444", bg=BG, font=("Arial", 10)).pack(pady=40)
            tk.Button(dlg, text="Đóng", command=on_close, bg=FIELD, fg="white",
                      relief="flat", borderwidth=0, padx=16, pady=6).pack()
            return

        # Filter bar
        filter_frame = tk.Frame(dlg, bg=PANEL, padx=16, pady=6)
        filter_frame.pack(fill=tk.X)
        tk.Label(filter_frame, text="Lọc:", fg=MUTED, bg=PANEL, font=("Arial", 9)).pack(side=tk.LEFT)
        type_filter_var = tk.StringVar(value="TẤT CẢ")
        types = ["TẤT CẢ"] + sorted({c['type'] for c in candidates})
        type_combo = ttk.Combobox(filter_frame, textvariable=type_filter_var, values=types,
                                  state="readonly", width=12, font=("Arial", 9))
        type_combo.pack(side=tk.LEFT, padx=(4, 12))
        min_conf_var = tk.IntVar(value=0)
        tk.Label(filter_frame, text="Điểm ≥", fg=MUTED, bg=PANEL, font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Spinbox(filter_frame, from_=0, to=99, textvariable=min_conf_var, width=4, bg=FIELD, fg="white",
                   insertbackground="white", relief="flat", font=("Arial", 9)).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(filter_frame, text="%", fg=MUTED, bg=PANEL, font=("Arial", 9)).pack(side=tk.LEFT, padx=(2, 12))
        search_var = tk.StringVar()
        tk.Label(filter_frame, text="Tìm:", fg=MUTED, bg=PANEL, font=("Arial", 9)).pack(side=tk.LEFT)
        search_entry = tk.Entry(filter_frame, textvariable=search_var, width=20, bg=FIELD, fg="white",
                                insertbackground="white", relief="flat", font=("Arial", 9))
        search_entry.pack(side=tk.LEFT, padx=(4, 0), ipady=2)
        tk.Label(filter_frame, text="Space: chọn · Del: bỏ qua · Enter: sửa bản dịch",
                 fg="#52525b", bg=PANEL, font=("Arial", 8)).pack(side=tk.RIGHT)

        # Bảng
        table = tk.Frame(dlg, bg=BG)
        table.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 0))
        columns = ("sel", "cn", "type", "count", "conf", "vi")
        tree = ttk.Treeview(table, columns=columns, show="headings", style="Scan.Treeview", selectmode="extended")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for col, text, width, anchor, stretch in (
                ("sel", "✓", 34, "center", False), ("cn", "Tiếng Trung", 130, "w", False),
                ("type", "Loại", 80, "center", False), ("count", "Xuất hiện", 80, "center", False),
                ("conf", "Điểm", 64, "center", False), ("vi", "Bản dịch đề xuất", 300, "w", True)):
            tree.heading(col, text=text, command=lambda c=col: sort_by(c))
            tree.column(col, width=width, minwidth=width if not stretch else 120, anchor=anchor, stretch=stretch)
        tree.tag_configure("odd", background="#1c1c1f")
        tree.tag_configure("checked", foreground="#c4b5fd")
        tree.tag_configure("empty", foreground="#f59e0b")

        # Khung chi tiết
        detail = tk.Frame(dlg, bg=PANEL, padx=12, pady=8)
        detail.pack(fill=tk.X, padx=12, pady=(6, 0))
        top_row = tk.Frame(detail, bg=PANEL)
        top_row.pack(fill=tk.X)
        detail_cn = tk.Label(top_row, text="—", fg="#ffffff", bg=PANEL, font=("Consolas", 14, "bold"))
        detail_cn.pack(side=tk.LEFT)
        detail_meta = tk.Label(top_row, text="", fg=MUTED, bg=PANEL, font=("Arial", 8))
        detail_meta.pack(side=tk.LEFT, padx=10)
        vi_row = tk.Frame(detail, bg=PANEL)
        vi_row.pack(fill=tk.X, pady=(6, 4))
        tk.Label(vi_row, text="Bản dịch:", fg="#10b981", bg=PANEL, font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        vi_var = tk.StringVar()
        vi_entry = tk.Entry(vi_row, textvariable=vi_var, bg=FIELD, fg="white", insertbackground="white",
                            relief="flat", font=("Arial", 11), highlightthickness=1,
                            highlightbackground="#3f3f46", highlightcolor="#7c3aed")
        vi_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, ipady=3)
        small = dict(relief="flat", borderwidth=0, padx=10, pady=3, font=("Arial", 8, "bold"), cursor="hand2", fg="white")
        tk.Button(vi_row, text="Copy Hán", bg="#1d4ed8", command=lambda: copy_chinese(), **small).pack(side=tk.LEFT, padx=2)
        tk.Button(vi_row, text="Thêm", bg="#059669", command=lambda: add_current(), **small).pack(side=tk.LEFT, padx=2)
        tk.Button(vi_row, text="Bỏ qua", bg="#3f3f46", command=lambda: ignore_rows(tree.selection()), **small).pack(side=tk.LEFT, padx=2)
        context_box = tk.Text(detail, height=4, wrap=tk.WORD, bg=BG, fg="#a1a1aa", font=("Consolas", 10),
                              borderwidth=0, padx=8, pady=4)
        context_box.pack(fill=tk.X)
        context_box.tag_configure("hit", foreground="#fde68a", background="#3f2d0a")
        context_box.config(state=tk.DISABLED)

        # Status bar
        status_var = tk.StringVar(value="")
        tk.Label(dlg, textvariable=status_var, fg="#10b981", bg=BG, font=("Arial", 8)).pack(anchor="w", padx=16, pady=4)

        by_cn = {c['cn']: c for c in candidates}
        ignored: set = set()
        edited_values = {c['cn']: c.get('suggested_vi', '') for c in candidates}
        selected = set()  # Review suggestions before selecting them for saving.
        sort_state = {"col": None, "reverse": False}
        current = {"cn": None}

        def row_values(c):
            cn = c['cn']
            return ("☑" if cn in selected else "☐", cn, c['type'], c['count'],
                    f"{int(c['confidence'] * 100)}%", edited_values[cn])

        def row_tags(c, index):
            tags = ["odd"] if index % 2 else []
            if c['cn'] in selected:
                tags.append("checked")
            if not edited_values[c['cn']].strip():
                tags.append("empty")
            return tags

        def matching_candidates():
            try:
                min_conf = min_conf_var.get()
            except tk.TclError:
                min_conf = 0
            filter_type = type_filter_var.get()
            query = search_var.get().strip().casefold()
            rows = [c for c in candidates
                    if c['cn'] not in ignored
                    and (filter_type == "TẤT CẢ" or c['type'] == filter_type)
                    and c['confidence'] * 100 >= min_conf
                    and (not query or query in c['cn'].casefold() or query in edited_values[c['cn']].casefold())]
            col = sort_state["col"]
            if col:
                keys = {"sel": lambda c: c['cn'] in selected, "cn": lambda c: c['cn'], "type": lambda c: c['type'],
                        "count": lambda c: c['count'], "conf": lambda c: c['confidence'],
                        "vi": lambda c: edited_values[c['cn']].casefold()}
                rows.sort(key=keys[col], reverse=sort_state["reverse"])
            return rows

        def rebuild(event=None):
            nonlocal filter_after_id
            filter_after_id = None
            focus = tree.focus()
            tree.delete(*tree.get_children())
            rows = matching_candidates()
            for index, c in enumerate(rows):
                tree.insert("", tk.END, iid=c['cn'], values=row_values(c), tags=row_tags(c, index))
            remaining = len([c for c in candidates if c['cn'] not in ignored])
            hdr_count_lbl.config(text=f"{remaining} ứng viên · đang hiện {len(rows)} · đã chọn {len(selected)}")
            if focus and tree.exists(focus):
                tree.focus(focus)
                tree.selection_set(focus)
                tree.see(focus)
            elif rows:
                tree.focus(rows[0]['cn'])
                tree.selection_set(rows[0]['cn'])
            else:
                show_detail(None)

        def refresh_row(cn):
            if cn in by_cn and tree.exists(cn):
                index = tree.index(cn)
                tree.item(cn, values=row_values(by_cn[cn]), tags=row_tags(by_cn[cn], index))
            hdr_count_lbl.config(text=f"{len([c for c in candidates if c['cn'] not in ignored])} ứng viên · "
                                      f"đang hiện {len(tree.get_children())} · đã chọn {len(selected)}")

        def schedule_filter(*_args):
            nonlocal filter_after_id
            if filter_after_id is not None:
                dlg.after_cancel(filter_after_id)
            filter_after_id = dlg.after(150, rebuild)

        def sort_by(col):
            if sort_state["col"] == col:
                sort_state["reverse"] = not sort_state["reverse"]
            else:
                sort_state["col"], sort_state["reverse"] = col, col in ("count", "conf", "sel")
            for name in columns:
                base = tree.heading(name, "text").rstrip(" ▲▼")
                arrow = (" ▼" if sort_state["reverse"] else " ▲") if name == col else ""
                tree.heading(name, text=base + arrow)
            rebuild()

        def show_detail(cn):
            current["cn"] = cn
            context_box.config(state=tk.NORMAL)
            context_box.delete("1.0", tk.END)
            if cn is None:
                detail_cn.config(text="—")
                detail_meta.config(text="")
                vi_var.set("")
            else:
                c = by_cn[cn]
                detail_cn.config(text=cn)
                signals = ", ".join(c.get('signals', []))
                detail_meta.config(text=f"{c['type']} · {c['count']} lần · điểm {int(c['confidence'] * 100)}%"
                                        + (f" · căn cứ: {signals}" if signals else ""))
                vi_var.set(edited_values[cn])
                for ctx in c.get('contexts', []) or ["(không có ngữ cảnh mẫu)"]:
                    start = context_box.index("end-1c")
                    context_box.insert(tk.END, "… " + ctx.replace("\n", " ") + " …\n")
                    pos = ctx.replace("\n", " ").find(cn)
                    while pos >= 0:
                        context_box.tag_add("hit", f"{start}+{pos + 2}c", f"{start}+{pos + 2 + len(cn)}c")
                        pos = ctx.replace("\n", " ").find(cn, pos + len(cn))
            context_box.config(state=tk.DISABLED)

        def on_select(event=None):
            focus = tree.focus()
            show_detail(focus if focus and focus in by_cn else None)

        def on_vi_change(*_args):
            cn = current["cn"]
            if cn is not None and edited_values.get(cn) != vi_var.get():
                edited_values[cn] = vi_var.get()
                refresh_row(cn)
        vi_var.trace_add("write", on_vi_change)

        def toggle(cns):
            cns = [cn for cn in cns if cn in by_cn]
            if not cns:
                return
            turn_on = any(cn not in selected for cn in cns)
            for cn in cns:
                if turn_on:
                    selected.add(cn)
                else:
                    selected.discard(cn)
                refresh_row(cn)

        def on_click(event):
            if tree.identify_region(event.x, event.y) == "cell" and tree.identify_column(event.x) == "#1":
                row = tree.identify_row(event.y)
                if row:
                    toggle([row])
                    return "break"
            return None

        def next_row_after(cns):
            children = tree.get_children()
            indexes = [children.index(cn) for cn in cns if cn in children]
            if not indexes:
                return None
            after = [c for c in children[max(indexes) + 1:] if c not in cns]
            before = [c for c in children[:min(indexes)] if c not in cns]
            return (after or before or [None])[0]

        def remove_rows(cns):
            following = next_row_after(cns)
            for cn in cns:
                selected.discard(cn)
                ignored.add(cn)
                if tree.exists(cn):
                    tree.delete(cn)
            if following:
                tree.focus(following)
                tree.selection_set(following)
                tree.see(following)
            else:
                show_detail(None)
            refresh_row("")

        def ignore_rows(cns):
            cns = [cn for cn in cns if cn in by_cn]
            if cns:
                remove_rows(cns)
                status_var.set(f"Đã bỏ qua: {', '.join(cns[:5])}{'…' if len(cns) > 5 else ''}")

        def copy_chinese():
            cn = current["cn"]
            if not cn:
                return
            dlg.clipboard_clear()
            dlg.clipboard_append(cn)
            vi_entry.focus_set()
            vi_entry.selection_range(0, tk.END)
            status_var.set(f"Đã copy chữ Hán: {cn}")

        def add_current(event=None):
            cn = current["cn"]
            if not cn:
                return "break"
            vi_text = edited_values[cn].strip()
            if not vi_text:
                messagebox.showwarning("Chú ý", "Vui lòng nhập tên tiếng Việt!", parent=dlg)
                return "break"
            if self._add_name_to_cfg(cn, vi_text, parent=dlg):
                remove_rows([cn])
                status_var.set(f"✅ Đã thêm: {cn} = {vi_text}")
                tree.focus_set()
            return "break"

        def focus_vi(event=None):
            if current["cn"]:
                vi_entry.focus_set()
                vi_entry.selection_range(0, tk.END)
            return "break"

        tree.bind("<<TreeviewSelect>>", on_select)
        tree.bind("<Button-1>", on_click)
        tree.bind("<space>", lambda e: (toggle(tree.selection()), "break")[1])
        tree.bind("<Delete>", lambda e: (ignore_rows(tree.selection()), "break")[1])
        tree.bind("<Return>", focus_vi)
        tree.bind("<Double-Button-1>", focus_vi)
        vi_entry.bind("<Return>", add_current)
        vi_entry.bind("<Escape>", lambda e: (tree.focus_set(), "break")[1])
        vi_entry.bind("<Down>", lambda e: (tree.focus_set(), tree.event_generate("<Down>"), "break")[2])
        vi_entry.bind("<Up>", lambda e: (tree.focus_set(), tree.event_generate("<Up>"), "break")[2])
        type_combo.bind("<<ComboboxSelected>>", rebuild)
        min_conf_var.trace_add("write", schedule_filter)
        search_var.trace_add("write", schedule_filter)
        dlg.bind("<Escape>", lambda e: on_close() if e.widget is not vi_entry else None)

        # Bottom bar: select and add in one batch (one name.cfg write).
        tk.Frame(dlg, bg=FIELD, height=1).pack(fill=tk.X, padx=12)
        bot = tk.Frame(dlg, bg=BG, pady=8)
        bot.pack(fill=tk.X, padx=12)

        def select_visible(value):
            for cn in tree.get_children():
                if value and edited_values[cn].strip():
                    selected.add(cn)
                elif not value:
                    selected.discard(cn)
                refresh_row(cn)

        def add_selected():
            entries = [(c['cn'], edited_values[c['cn']].strip()) for c in candidates
                       if c['cn'] in selected and c['cn'] not in ignored and edited_values[c['cn']].strip()]
            missing = sum(1 for cn in selected if cn not in ignored and not edited_values[cn].strip())
            if not entries:
                messagebox.showwarning("Chú ý", "Chưa chọn tên nào có bản dịch tiếng Việt.", parent=dlg)
                return
            if not self._add_names_to_cfg(entries, parent=dlg):
                return
            remove_rows([cn for cn, _vi in entries])
            suffix = f"; bỏ qua {missing} mục trống" if missing else ""
            status_var.set(f"✅ Đã lưu {len(entries)} tên vào name.cfg{suffix}")

        bar_btn = dict(relief="flat", borderwidth=0, padx=10, pady=6, font=("Arial", 8), cursor="hand2")
        tk.Button(bot, text="Chọn mục đang hiện (có bản dịch)", bg=FIELD, fg="#d4d4d8",
                  command=lambda: select_visible(True), **bar_btn).pack(side=tk.LEFT)
        tk.Button(bot, text="Bỏ chọn đang hiện", bg=FIELD, fg=MUTED,
                  command=lambda: select_visible(False), **bar_btn).pack(side=tk.LEFT, padx=4)
        tk.Button(bot, text="Đóng", bg=FIELD, fg=MUTED, activebackground="#3f3f46", relief="flat", borderwidth=0,
                  padx=16, pady=6, font=("Arial", 9), cursor="hand2", command=on_close).pack(side=tk.RIGHT, padx=(6, 0))
        tk.Button(bot, text="✅ Thêm các mục đã chọn", bg="#7c3aed", fg="white", activebackground="#6d28d9",
                  relief="flat", borderwidth=0, padx=16, pady=6, font=("Arial", 9, "bold"), cursor="hand2",
                  command=add_selected).pack(side=tk.RIGHT)

        rebuild()
        tree.focus_set()

    def _name_cfg_path(self):
        return name_cfg_path()

    def _add_names_to_cfg(self, entries, parent=None):
        """Validate and persist several names using one atomic file replacement."""
        try:
            update_name_cfg(self._name_cfg_path(), entries)
            return True
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi name.cfg:\n{e}", parent=parent or self.root)
            return False

    def _add_name_to_cfg(self, cn: str, vi: str, parent=None):
        return self._add_names_to_cfg([(cn, vi)], parent=parent)

    # ─────────────────────────────────────────────────────────────
    # DỊCH (luồng nền chỉ gửi cập nhật giao diện qua call_ui)
    # ─────────────────────────────────────────────────────────────

    def _set_busy(self, busy):
        if busy:
            self.btn_run.config(state="disabled")
            self.btn_clear.pack_forget()
            self.btn_cancel.config(state="normal", text="⏹ Huỷ")
            self.btn_cancel.pack(side="right", padx=5, before=self.btn_run)
            self.progress.config(value=0, maximum=1)
            self.progress.pack(fill="x", padx=20, before=self.lbl_status)
        else:
            self.btn_cancel.pack_forget()
            self.progress.pack_forget()

    def cancel_translation(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.btn_cancel.config(state="disabled", text="Đang dừng…")
            self.set_status("Đang dừng sau đợt hiện tại…", "#f59e0b")

    def start_thread(self):
        """Main thread: read and validate inputs, then translate in the background."""
        if self._worker is not None and self._worker.is_alive():
            return
        title = self.ent_title.get().strip()
        content = self.txt_area.get(1.0, tk.END).strip()
        if not title or not content:
            messagebox.showwarning("Chú ý", "Vui lòng nhập tiêu đề và nội dung!")
            self.btn_run.config(state="normal")
            return
        slug = slugify_vn(title)
        if not slug:
            messagebox.showwarning("Chú ý", "Tiêu đề không hợp lệ, không thể tạo slug!")
            self.btn_run.config(state="normal")
            return

        self._cancel_event = threading.Event()
        self._set_busy(True)
        self.set_status(f"Slug: {slug} — Đang xử lý dữ liệu...", "#3b82f6")
        self._worker = threading.Thread(target=self.run_process, args=(title, slug, content, self._cancel_event), daemon=True)
        self._worker.start()

    def _update_progress(self, done, total, started):
        self.progress.config(maximum=max(total, 1), value=done)
        text = f"Đang dịch đợt {min(done + 1, total)}/{total}"
        if done:
            remaining = (time.time() - started) / done * (total - done)
            text += f" · còn ~{remaining / 60:.0f} phút" if remaining >= 90 else f" · còn ~{remaining:.0f} giây"
        self.set_status(text + "...", "#3b82f6")

    def run_process(self, title, slug, content, cancel):
        """Worker thread. Never touch Tk widgets here."""
        try:
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            name_dict = self.load_name_config()
            source_pattern = compile_name_source_pattern(name_dict)
            processed_lines = [(line, substitute_names(line, name_dict, source_pattern)) for line in lines]

            chunks = split_translation(processed_lines)
            vi_names = list(name_dict.values())
            name_pattern = compile_name_pattern(vi_names)
            spacing_pattern = compile_name_loose_pattern(vi_names)
            final_cn_lines, final_vi_lines = [], []
            started = time.time()

            for i, group in enumerate(chunks):
                if cancel.is_set():
                    break
                self.call_ui(self._update_progress, i, len(chunks), started)
                vi_lines = self.translate_lines([rep for _, rep in group], cancel)
                for j, (orig_cn, _rep_cn) in enumerate(group):
                    vi = vi_lines[j] if j < len(vi_lines) else ""
                    vi = re.sub(r'  +', ' ', vi).strip()  # dấu cách kép do từ không dịch được
                    vi = fix_name_spacing(vi, spacing_pattern)
                    vi = fix_capitalization_after_names(vi, vi_names, name_pattern)
                    final_cn_lines.append(orig_cn)
                    final_vi_lines.append(vi)
                if i + 1 < len(chunks):
                    cancel.wait(DELAY)

            self.call_ui(self._translation_finished, title, slug, final_cn_lines, final_vi_lines,
                         cancel.is_set(), len(lines))
        except Exception as error:
            self.call_ui(self._translation_failed, error)

    def _translation_failed(self, error):
        self._set_busy(False)
        self.btn_run.config(state="normal")
        self.btn_clear.pack(side="right", padx=5)
        self.set_status("❌ Lỗi khi dịch", "#ef4444")
        messagebox.showerror("Lỗi", f"Lỗi khi dịch:\n{error}")

    def _translation_finished(self, title, slug, cn_lines, vi_lines, cancelled, total):
        self._set_busy(False)
        if cancelled:
            if cn_lines and messagebox.askyesno(
                    "Đã huỷ", f"Đã dịch {len(cn_lines)}/{total} đoạn trước khi huỷ.\nMở Review với phần đã dịch?"):
                self.set_status(f"Đã huỷ — xem {len(cn_lines)}/{total} đoạn đã dịch", "#f59e0b")
                ReviewWindow(self.root, title, slug, cn_lines, vi_lines, self)
            else:
                self.btn_run.config(state="normal")
                self.btn_clear.pack(side="right", padx=5)
                self.set_status("Đã huỷ dịch.", "#f59e0b")
            return
        self.set_status("Hoàn tất dịch API. Đang mở cửa sổ Review...", "#f59e0b")
        ReviewWindow(self.root, title, slug, cn_lines, vi_lines, self)


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = TranslatorGUI(root)
    root.mainloop()
