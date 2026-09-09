import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import requests, json, os, sys, base64, datetime, time, threading
import unicodedata, re
from tkinterdnd2 import TkinterDnD, DND_FILES
try:
    import han_viet as _hv
    _HAN_VIET_OK = True
except ImportError:
    _HAN_VIET_OK = False


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
CHUNK_LIMIT = 12000
DELAY = 1.2
CONFIG_PATH = os.path.join(BASE_DIR, "editor_config.json")


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

# --- CLASS REVIEW WINDOW MỚI ---
class ReviewWindow:
    def __init__(self, parent, title, slug, cn_lines, vi_lines, app_instance):
        self.top = tk.Toplevel(parent)
        self.top.title(f"Review & Edit Name: {title}")
        self.top.configure(bg="#09090b")
        
        self.title = title
        self.slug = slug
        self.cn_lines = cn_lines
        self.vi_lines = vi_lines
        self.app = app_instance

        # Restore saved geometry or use default
        cfg = load_config()
        geo = cfg.get("builder_review", "900x700")
        self.top.geometry(geo)

        self.top.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.setup_ui()
        self.load_content()

    def on_closing(self):
        save_config({"builder_review": self.top.geometry()})
        self.app.btn_run.config(state="normal")
        self.app.lbl_status.config(text="Sẵn sàng", fg="#71717a")
        self.app.btn_clear.pack(side="right", padx=5)
        self.top.destroy()


    def setup_ui(self):
        ctrl_frame = tk.Frame(self.top, bg="#09090b")
        ctrl_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(ctrl_frame, text="Bôi đen chữ bên dưới ➡️ Click chuột phải để Thêm Name", fg="#a1a1aa", bg="#09090b").pack(side="left")
        
        btn_save = tk.Button(ctrl_frame, text="💾 Lưu vào data.json", command=self.save_data, bg="#10b981", fg="white", borderwidth=0, padx=15)
        btn_save.pack(side="right")
        
        btn_add = tk.Button(ctrl_frame, text="✏️ Thêm Name thủ công", command=self.prompt_add_name, bg="#3b82f6", fg="white", borderwidth=0, padx=15)
        btn_add.pack(side="right", padx=(0, 10))

        btn_retrans = tk.Button(ctrl_frame, text="🔄 Dịch Lại Toàn Bộ", command=self.retranslate_all, bg="#f59e0b", fg="white", borderwidth=0, padx=15)
        btn_retrans.pack(side="right", padx=(0, 10))

        btn_check_errors = tk.Button(ctrl_frame, text="🔍 Kiểm tra lỗi dịch", command=self.check_translation_errors, bg="#ef4444", fg="white", borderwidth=0, padx=15)
        btn_check_errors.pack(side="right", padx=(0, 10))

        self.text_editor = scrolledtext.ScrolledText(self.top, wrap=tk.WORD, bg="#18181b", fg="#e4e4e7", font=("Consolas", 11), borderwidth=0)
        self.text_editor.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.text_editor.tag_config("cn", foreground="#71717a")
        self.text_editor.tag_config("vi", foreground="#ffffff")
        
        self.menu = tk.Menu(self.top, tearoff=0, bg="#27272a", fg="white", borderwidth=0)
        self.menu.add_command(label="Sửa lỗi & Thêm Name", command=self.prompt_add_name)
        
        self.text_editor.bind("<Button-3>", self.show_context_menu)

    def retranslate_all(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn dịch lại toàn bộ truyện không? (Sẽ tốn thời gian gọi API từ đầu)", parent=self.top):
            self.app.btn_run.config(state="normal")
            self.top.destroy()
            self.app.start_thread()

    def check_translation_errors(self):
        self.text_editor.tag_remove("error_highlight", "1.0", tk.END)
        self.text_editor.tag_config("error_highlight", background="#ef4444", foreground="white")
        
        import re
        # Tìm các ký tự Hán (bao gồm cả các bộ mở rộng) và ký tự lỗi Unicode \ufffd ()
        error_pattern = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\ufffd]')

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
            messagebox.showwarning("Phát hiện lỗi", f"Tìm thấy {error_count} chỗ có ký tự tiếng Trung chưa được dịch hoặc ký tự bị lỗi font ().\nĐã bôi đỏ các chỗ này.", parent=self.top)
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
        
        # Bắt buộc Tkinter tính toán lại giao diện trước khi cuộn
        self.text_editor.update_idletasks()
        
        # Phục hồi vị trí con trỏ (để tránh Tkinter auto-scroll về dòng 1 khi focus)
        self.text_editor.mark_set("insert", insert_pos)
        
        # Phục hồi vị trí cuộn (kết hợp after để chống hiện tượng giật muộn của Tkinter)
        self.text_editor.yview_moveto(scroll_pos[0])
        self.text_editor.after(10, lambda: self.text_editor.yview_moveto(scroll_pos[0]))
        self.text_editor.after(50, lambda: self.text_editor.yview_moveto(scroll_pos[0]))
        self.text_editor.after(100, lambda: self.text_editor.yview_moveto(scroll_pos[0]))

    def show_context_menu(self, event):
        try:
            self.text_editor.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.menu.tk_popup(event.x_root, event.y_root)
        except tk.TclError:
            pass

    def prompt_add_name(self):
        try:
            selected_text = self.text_editor.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
        except tk.TclError:
            selected_text = ""

        import re

        # Check xem chuỗi bôi đen có chứa ký tự CJK (Tiếng Trung) không
        is_cn = any('\u4e00' <= char <= '\u9fff' for char in selected_text)

        dialog = tk.Toplevel(self.top)
        dialog.title("Sửa lỗi & Thêm Name Mới")
        dialog.configure(bg="#18181b")
        dialog.transient(self.top)
        dialog.grab_set()

        # Restore saved geometry or default
        _cfg = load_config()
        _geo = _cfg.get("builder_add_name", "420x350")
        try:
            dialog.geometry(_geo)
        except Exception:
            dialog.geometry("420x350")
        dialog.resizable(True, True)


        # 1. Ô Tiếng Trung
        tk.Label(dialog, text="1. Tiếng Trung gốc (để lưu Name dùng vĩnh viễn):", fg="#a1a1aa", bg="#18181b").pack(pady=(10,0), anchor="w", padx=20)
        ent_cn = tk.Entry(dialog, bg="#27272a", fg="white", borderwidth=0, insertbackground="white")
        ent_cn.pack(fill="x", padx=20, pady=5, ipady=5)
        if is_cn and selected_text:
            ent_cn.insert(0, selected_text)

        # 2. Ô Từ sai
        tk.Label(dialog, text="2. Cụm từ VN bị dịch sai (để thay thế trong bài này):", fg="#a1a1aa", bg="#18181b").pack(pady=(10,0), anchor="w", padx=20)
        ent_wrong = tk.Entry(dialog, bg="#27272a", fg="white", borderwidth=0, insertbackground="white")
        ent_wrong.pack(fill="x", padx=20, pady=5, ipady=5)
        if not is_cn and selected_text:
            ent_wrong.insert(0, selected_text)

        # 3. Ô Name đúng
        tk.Label(dialog, text="3. Sửa thành (Name đúng):", fg="#10b981", bg="#18181b", font=("Arial", 10, "bold")).pack(pady=(10,0), anchor="w", padx=20)
        ent_right = tk.Entry(dialog, bg="#27272a", fg="white", borderwidth=0, insertbackground="white")
        ent_right.pack(fill="x", padx=20, pady=5, ipady=5)
        
        if is_cn and selected_text:
            # Gợi ý Name bằng cách gọi API dịch tiếng Trung và tự title-case
            import threading
            def fetch_suggestion(cn_text):
                try:
                    res = self.app.translate_api(cn_text)
                    if res:
                        # API trả về text thuần (VD: 'Lâm Vũ hân'), chỉ cần title-case
                        suggestion = res.strip().title()
                        
                        if suggestion:
                            def safe_insert():
                                if not ent_right.get():
                                    ent_right.insert(0, suggestion)
                            dialog.after(0, safe_insert)
                except Exception:
                    pass
            threading.Thread(target=fetch_suggestion, args=(selected_text,), daemon=True).start()

        def apply_name(retranslate=False):
            cn_val = ent_cn.get().strip()
            wrong_val = ent_wrong.get().strip()
            right_val = ent_right.get().strip()

            # Chuẩn hóa NFC để so sánh chính xác các ký tự tiếng Việt
            if cn_val: cn_val = unicodedata.normalize('NFC', cn_val)
            if wrong_val: wrong_val = unicodedata.normalize('NFC', wrong_val)
            if right_val: right_val = unicodedata.normalize('NFC', right_val)

            if not right_val:
                messagebox.showwarning("Chú ý", "Vui lòng nhập 'Name đúng'!", parent=dialog)
                return

            if retranslate:
                if not cn_val:
                    messagebox.showwarning("Chú ý", "Để dịch lại từ đầu, bắt buộc phải có 'Tiếng Trung gốc'!", parent=dialog)
                    return
                self.save_name_to_cfg(cn_val, right_val)
                self.app.btn_run.config(state="normal")
                save_config({"builder_add_name": dialog.geometry()})
                dialog.destroy()
                self.top.destroy()
                self.app.start_thread()
                return


            import re
            
            # Tự động gọi API để tìm từ bị dịch sai nếu người dùng để trống Ô 2
            if not wrong_val and cn_val:
                try:
                    self.app.lbl_status.config(text="Đang tự động tìm từ dịch sai qua API...", fg="#f59e0b")
                    self.app.root.update()
                    auto_vi = self.app.translate_api(cn_val)
                    if auto_vi:
                        wrong_val = unicodedata.normalize('NFC', auto_vi.strip())
                except Exception:
                    pass

            if not wrong_val and not cn_val:
                messagebox.showwarning("Chú ý", "Vui lòng nhập ít nhất 'Tiếng Trung' hoặc 'Từ sai'!", parent=dialog)
                return

            if not wrong_val:
                if not messagebox.askyesno("Xác nhận", "Bạn chưa nhập 'Cụm từ VN bị dịch sai' (Ô số 2) và hệ thống không thể tự động nhận diện.\n\nHệ thống sẽ lưu Name vào từ điển để áp dụng cho các chương sau, nhưng SẼ KHÔNG THỂ cập nhật nhanh trong đoạn text hiện tại.\n\nBạn có muốn tiếp tục?", parent=dialog):
                    return

            # Replace toàn bộ chữ sai thành chữ đúng trên mảng RAM (áp dụng cho TOÀN BỘ file truyện)
            name_words_set = set(right_val.split())
            for i in range(len(self.vi_lines)):
                # 1. Thay thế global nếu người dùng có nhập wrong_val
                if wrong_val:
                    # Dùng Regex để thay thế không phân biệt hoa thường (case-insensitive)
                    pattern_wrong = re.compile(re.escape(wrong_val), re.IGNORECASE)
                    self.vi_lines[i] = pattern_wrong.sub(right_val, self.vi_lines[i])
                    self.vi_lines[i] = unicodedata.normalize('NFC', self.vi_lines[i])
                    
                    # Sửa lỗi viết hoa của chữ đi ngay sau name
                    pattern_fix = re.compile(re.escape(right_val) + r'(\s+)([\w]+)', re.UNICODE)
                    def replacer(match):
                        space = match.group(1)
                        word = match.group(2)
                        if word.istitle() and word not in name_words_set:
                            return right_val + space + word.lower()
                        return match.group(0)
                    self.vi_lines[i] = pattern_fix.sub(replacer, self.vi_lines[i])



            # Ghi Tiếng Trung = Name đúng vào file config
            if cn_val:
                self.save_name_to_cfg(cn_val, right_val)

            # Cập nhật trực tiếp lên màn hình mà không xóa đi nạp lại, CHỐNG NHẢY CHUỘT 100%
            self.text_editor.config(state=tk.NORMAL)
            for i in range(len(self.vi_lines)):
                line_idx = i * 3 + 2
                self.text_editor.delete(f"{line_idx}.0", f"{line_idx}.end")
                self.text_editor.insert(f"{line_idx}.0", self.vi_lines[i], "vi")
            self.text_editor.config(state=tk.DISABLED)
            
            save_config({"builder_add_name": dialog.geometry()})
            dialog.destroy()


        btn_frame = tk.Frame(dialog, bg="#18181b")
        btn_frame.pack(pady=20)
        
        tk.Button(btn_frame, text="🚀 Cập nhật nhanh", command=lambda: apply_name(False), bg="#3b82f6", fg="white", borderwidth=0).pack(side="left", padx=10, ipadx=10, ipady=5)
        tk.Button(btn_frame, text="🔄 Dịch Lại Toàn Bộ", command=lambda: apply_name(True), bg="#f59e0b", fg="white", borderwidth=0).pack(side="left", padx=10, ipadx=10, ipady=5)

    def save_name_to_cfg(self, cn, vi):
        if getattr(sys, 'frozen', False):
            cfg_dir = os.path.dirname(sys.executable)
        else:
            cfg_dir = BASE_DIR
        cfg_path = os.path.join(cfg_dir, "name.cfg")
        
        try:
            if not os.path.exists(cfg_path):
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(f"{cn}={vi}\n")
                return

            with open(cfg_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            found = False
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == cn:
                        if val.strip() != vi:
                            lines[i] = f"{cn}={vi}\n"
                        found = True
                        break
            
            if not found:
                if lines and not lines[-1].endswith("\n"):
                    lines.append("\n")
                lines.append(f"{cn}={vi}\n")
                
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            print(f"Lỗi khi lưu name.cfg: {e}")

    def save_data(self):
        output_dir = os.path.join(BASE_DIR, "stories", self.slug)
        os.makedirs(output_dir, exist_ok=True)
        
        story_data = {"title": self.title, "content": []}
        
        for i in range(len(self.cn_lines)):
            cn_nfc = unicodedata.normalize('NFC', self.cn_lines[i])
            vi_nfc = unicodedata.normalize('NFC', self.vi_lines[i])
            
            # Loại bỏ dấu cách kép (nếu có)
            vi_clean = re.sub(r'  +', ' ', vi_nfc).strip()
            # Re-normalize NFC sau regex để đảm bảo ký tự tiếng Việt không bị decomposed
            vi_clean = unicodedata.normalize('NFC', vi_clean)
            
            story_data["content"].append({
                "cn": base64.b64encode(cn_nfc.encode('utf-8')).decode('utf-8'),
                "vi": base64.b64encode(vi_clean.encode('utf-8')).decode('utf-8')
            })

        with open(os.path.join(output_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(story_data, f, ensure_ascii=False)

        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f_t, open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f_i:
                f_i.write(f_t.read())

        self.app.update_catalog(self.title, self.slug)
        self.app.lbl_status.config(text="✅ Đã lưu data.json thành công!", fg="#10b981")
        self.app.btn_run.config(state="normal")
        self.app.btn_clear.pack(side="right", padx=5)
        messagebox.showinfo("Thành công", f"Đã xuất dữ liệu truyện: {self.slug}")
        self.top.destroy()

# --- CLASS GIAO DIỆN CHÍNH ---
class TranslatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Story Translator Pro - SangTacViet API")
        self.root.configure(bg="#09090b")
        self._resize_timer = None

        # Restore saved geometry or use default
        cfg = load_config()
        geo = cfg.get("builder_main", "700x600")
        self.root.geometry(geo)

        # UI Components
        self.setup_ui()

        # Save geometry on resize (debounced)
        self.root.bind("<Configure>", self._on_root_configure)

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
        tk.Label(self.root, text="DỊCH TRUYỆN TRUNG - VIỆT", font=("Arial", 14, "bold"), fg="#ffffff", bg="#09090b").pack(pady=10)

        # Story Title Input
        frame_title = tk.Frame(self.root, bg="#09090b")
        frame_title.pack(fill="x", padx=20, pady=5)
        tk.Label(frame_title, text="Story Title:", fg="#a1a1aa", bg="#09090b").pack(side="left")
        self.ent_title = tk.Entry(frame_title, bg="#18181b", fg="#ffffff", insertbackground="white", borderwidth=0)
        self.ent_title.pack(side="left", fill="x", expand=True, padx=10, ipady=5)

        # Text Area for Copy-Paste
        tk.Label(self.root, text="Nội dung tiếng Trung (hoặc kéo thả / chọn file .txt):", fg="#a1a1aa", bg="#09090b").pack(anchor="w", padx=20, pady=(10, 0))
        self.txt_area = scrolledtext.ScrolledText(self.root, height=15, bg="#18181b", fg="#e4e4e7", borderwidth=0, font=("Consolas", 10))
        self.txt_area.pack(fill="both", expand=True, padx=20, pady=5)

        # Drop Zone
        self.drop_zone = tk.Label(
            self.root, text="📂  Kéo thả file .txt vào đây",
            bg="#18181b", fg="#71717a", font=("Arial", 10),
            relief="groove", borderwidth=2, pady=12
        )
        self.drop_zone.pack(fill="x", padx=20, pady=(0, 5))
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.handle_drop)
        self.drop_zone.dnd_bind("<<DragEnter>>", lambda e: self.drop_zone.config(bg="#27272a", fg="#3b82f6"))
        self.drop_zone.dnd_bind("<<DragLeave>>", lambda e: self.drop_zone.config(bg="#18181b", fg="#71717a"))

        # Buttons Frame
        btn_frame = tk.Frame(self.root, bg="#09090b")
        btn_frame.pack(fill="x", padx=20, pady=10)

        self.btn_file = tk.Button(btn_frame, text="📁 Chọn File .txt", command=self.load_file, bg="#27272a", fg="white", borderwidth=0, padx=15)
        self.btn_file.pack(side="left", padx=5)

        self.btn_scan = tk.Button(btn_frame, text="🔍 Scan Names", command=self.open_scan_names_dialog, bg="#7c3aed", fg="white", borderwidth=0, padx=15)
        self.btn_scan.pack(side="left", padx=5)

        self.btn_run = tk.Button(btn_frame, text="🚀 Bắt đầu dịch", command=self.start_thread, bg="#1d4ed8", fg="white", borderwidth=0, padx=25)
        self.btn_run.pack(side="right", padx=5)

        self.btn_clear = tk.Button(btn_frame, text="🗑️ Xóa tất cả", command=self.clear_all, bg="#dc2626", fg="white", borderwidth=0, padx=15)

        # Progress Label
        self.lbl_status = tk.Label(self.root, text="Sẵn sàng", fg="#71717a", bg="#09090b")
        self.lbl_status.pack(pady=5)

    def clear_all(self):
        self.ent_title.delete(0, tk.END)
        self.txt_area.delete(1.0, tk.END)
        self.lbl_status.config(text="Sẵn sàng", fg="#71717a")
        self.btn_clear.pack_forget()

    def handle_drop(self, event):
        self.drop_zone.config(bg="#18181b", fg="#71717a")
        raw = event.data
        if raw.startswith("{"):
            file_path = raw.strip("{}") 
        else:
            file_path = raw.strip()
        if not file_path.lower().endswith(".txt"):
            messagebox.showwarning("Chú ý", "Chỉ hỗ trợ file .txt!")
            return
        self._load_from_path(file_path)

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if file_path:
            self._load_from_path(file_path)

    def _load_from_path(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.txt_area.delete(1.0, tk.END)
                self.txt_area.insert(tk.END, f.read())
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file:\n{e}")
            return

        title_suggest = os.path.basename(file_path).replace(".txt", "")
        self.ent_title.delete(0, tk.END)
        self.ent_title.insert(0, title_suggest)
        self.lbl_status.config(text=f"Đã tải: {os.path.basename(file_path)}", fg="#10b981")

    def update_catalog(self, title, slug):
        stories_dir = os.path.join(BASE_DIR, "stories")
        catalog_path = os.path.join(stories_dir, "list.json")
        os.makedirs(stories_dir, exist_ok=True)
        catalog = []
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
            except: pass

        existing = next((item for item in catalog if item.get('slug') == slug), None)
        now = datetime.datetime.now()
        if not existing:
            catalog.append({"title": title, "slug": slug, "date": now.strftime("%d/%m/%Y"), "timestamp": now.timestamp()})
        else:
            existing['date'] = now.strftime("%d/%m/%Y")
            existing['timestamp'] = now.timestamp()

        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=4)

    def load_name_config(self):
        if getattr(sys, 'frozen', False):
            cfg_dir = os.path.dirname(sys.executable)
        else:
            cfg_dir = BASE_DIR
            
        cfg_path = os.path.join(cfg_dir, "name.cfg")
        
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
                with open(cfg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            cn, vi = line.split("=", 1)
                            if cn.strip() and vi.strip():
                                name_dict[cn.strip()] = vi.strip().title()
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
        except: return None

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

    def scan_name_candidates(self, text: str, max_results: int = 250) -> list:
        """
        Scan Chinese text and return candidate names/terms sorted by confidence.
        Optimized O(N) algorithm with background execution support.
        """
        import collections

        existing_glossary: set = set()
        name_dict = self.load_name_config()
        existing_glossary = set(name_dict.keys())

        single_surnames = _hv.SINGLE_SURNAMES if _HAN_VIET_OK else set()
        double_surnames = _hv.DOUBLE_SURNAMES if _HAN_VIET_OK else []
        context_patterns = _hv.CONTEXT_PATTERNS if _HAN_VIET_OK else []
        entity_suffixes = _hv.ENTITY_SUFFIXES if _HAN_VIET_OK else {}
        stopwords = _hv.STOPWORD_TERMS if _HAN_VIET_OK else set()
        invalid_chars = getattr(_hv, 'INVALID_NAME_CHARS', set('的了着是在有不是一个去到进出过要能会看说道问笑摇头走死把被为与及或等这那它他她已乃从自向即又但虽却并手声色身步面眼心冷沉怒厉淡微苦大小老少归回来'))

        # ── 1. Segment text by punctuation ──
        segments = re.split(r'[，。！？、“”‘’：；…\n\r\t ()（）《》【】—\-.,!?:;\'"~]+', text)
        segments = [s.strip() for s in segments if s.strip()]

        # ── 2. Count n-grams (2–6 chars) in one pass ──
        ngram_freq = collections.Counter()
        for seg in segments:
            seg_cjk = ''.join(c for c in seg if self._is_cjk(c))
            L = len(seg_cjk)
            for n in range(2, min(7, L + 1)):
                for i in range(L - n + 1):
                    ngram_freq[seg_cjk[i:i+n]] += 1

        # ── 3. Context pattern hits (X说道, X冷笑道, X看着, X长老...) ──
        context_hits: dict = collections.defaultdict(int)
        context_examples: dict = collections.defaultdict(list)
        for pat in context_patterns:
            for m in re.finditer(pat, text):
                cand = m.group(1).strip()
                while cand and cand[0] in invalid_chars:
                    cand = cand[1:]
                while cand and cand[-1] in invalid_chars:
                    cand = cand[:-1]
                if 2 <= len(cand) <= 4 and all(self._is_cjk(c) for c in cand):
                    context_hits[cand] += 1
                    if len(context_examples[cand]) < 3:
                        start = max(0, m.start() - 6)
                        end = min(len(text), m.end() + 6)
                        context_examples[cand].append(text[start:end].replace('\n', ' '))

        # ── 4. Surname heuristic (2-3 chars for single, 3-4 chars for double) ──
        surname_hits: set = set()
        for seg in segments:
            seg_cjk = ''.join(c for c in seg if self._is_cjk(c))
            # Double surname: length 3 or 4
            for ds in double_surnames:
                idx = 0
                while True:
                    pos = seg_cjk.find(ds, idx)
                    if pos == -1:
                        break
                    for L in (3, 4):
                        if pos + L <= len(seg_cjk):
                            cand = seg_cjk[pos:pos+L]
                            if not any(c in invalid_chars for c in cand[len(ds):]):
                                surname_hits.add(cand)
                    idx = pos + 1

            # Single surname or "阿" prefix (2 or 3 chars, e.g. 阿宝, 林铭)
            for i, ch in enumerate(seg_cjk):
                if ch in single_surnames or ch == '阿':
                    for L in (2, 3):
                        if i + L <= len(seg_cjk):
                            cand = seg_cjk[i:i+L]
                            if not any(c in invalid_chars for c in cand[1:]):
                                surname_hits.add(cand)

        # ── 5. Entity suffix hits from frequent n-grams ──
        entity_hits: set = set()
        for ngram, cnt in ngram_freq.items():
            if cnt >= 2 and len(ngram) in (2, 3, 4, 5):
                if ngram[-1] in entity_suffixes:
                    if not any(c in invalid_chars for c in (ngram[0], ngram[-1])):
                        entity_hits.add(ngram)

        # ── 6. Candidate Pool ──
        pool: set = set()
        pool.update(context_hits.keys())
        pool.update(surname_hits)
        pool.update(entity_hits)
        # Frequent terms (count >= 3, length 2-3)
        for ngram, cnt in ngram_freq.items():
            if cnt >= 3 and len(ngram) in (2, 3):
                if not any(c in invalid_chars for c in (ngram[0], ngram[-1])):
                    if ngram not in stopwords:
                        pool.add(ngram)

        # ── 7. Fast O(N) Sub-ngram suppression ──
        sorted_cands = sorted(pool, key=len, reverse=True)
        to_remove = set()
        cand_set = set(pool)

        for super_cand in sorted_cands:
            if super_cand in to_remove:
                continue
            super_cnt = ngram_freq.get(super_cand, 0)
            L = len(super_cand)
            for sub_len in range(2, L):
                for i in range(L - sub_len + 1):
                    sub = super_cand[i:i+sub_len]
                    if sub in cand_set and sub not in to_remove:
                        sub_cnt = ngram_freq.get(sub, 0)
                        if sub_cnt <= super_cnt * 1.1:
                            to_remove.add(sub)
                        elif sub in double_surnames and super_cand.startswith(sub):
                            to_remove.add(sub)

        pool -= to_remove

        # ── 8. Score & classify ──
        results = []
        for cand in pool:
            if cand in existing_glossary or cand in stopwords:
                continue
            if len(cand) < 2 or not all(self._is_cjk(c) for c in cand):
                continue
            if any(c in invalid_chars for c in (cand[0], cand[-1])):
                continue

            cnt = ngram_freq.get(cand, 1)
            ctx_score = context_hits.get(cand, 0)
            has_ds = any(cand.startswith(ds) for ds in double_surnames) and len(cand) in (3, 4)
            has_ss = (cand[0] in single_surnames) and len(cand) in (2, 3)
            has_a = cand.startswith('阿') and len(cand) in (2, 3)
            has_surname = has_ds or has_ss or has_a

            # Filter out single-occurrence accidental surname substrings (e.g. 任何, 告诉)
            if has_surname and cnt == 1 and ctx_score == 0:
                continue

            last_ch = cand[-1]
            has_suffix = last_ch in entity_suffixes

            # Entity type (Person takes precedence if has name signal)
            if has_surname or ctx_score > 0:
                etype = 'PERSON'
            elif has_suffix:
                etype = entity_suffixes[last_ch]
            else:
                etype = 'UNKNOWN'

            # Confidence 0..1
            conf = 0.0
            if ctx_score > 0:
                conf += min(0.50, 0.20 * ctx_score)
            if has_surname:
                conf += 0.35
            if has_suffix:
                conf += 0.30
            if cnt >= 2:
                conf += 0.15
            if cnt >= 4:
                conf += 0.15
            if cnt >= 8:
                conf += 0.10
            conf = min(conf, 0.99)

            if conf < 0.25 and cnt < 2:
                continue


            results.append({
                'cn': cand,
                'type': etype,
                'count': cnt,
                'confidence': conf,
                'contexts': context_examples.get(cand, []),
                'suggested_vi': self._suggest_vi(cand),
            })

        # Sort: confidence desc, count desc, length asc
        results.sort(key=lambda x: (-x['confidence'], -x['count'], len(x['cn'])))
        return results[:max_results]

    def open_scan_names_dialog(self):
        """Open the Scan Names dialog."""
        raw_text = self.txt_area.get(1.0, tk.END).strip()
        if not raw_text:
            messagebox.showwarning("Chú ý", "Vui lòng nhập nội dung tiếng Trung trước!")
            return

        self.root.config(cursor="watch")
        self.btn_scan.config(state="disabled", text="⏳ Đang quét...")
        self.root.update_idletasks()

        try:
            candidates = self.scan_name_candidates(raw_text)
        except Exception as e:
            self.root.config(cursor="")
            self.btn_scan.config(state="normal", text="🔍 Scan Names")
            messagebox.showerror("Lỗi", f"Lỗi khi quét tên:\n{e}")
            return
        finally:
            self.root.config(cursor="")
            self.btn_scan.config(state="normal", text="🔍 Scan Names")

        self.lbl_status.config(text=f"Đã quét xong: tìm thấy {len(candidates)} ứng viên")
        self._show_scan_names_dialog(candidates)

    def _show_scan_names_dialog(self, candidates):

        """Build and display the Scan Names dialog."""
        dlg = tk.Toplevel(self.root)
        dlg.title("🔍 Scan Names — Danh sách tên phát hiện")
        dlg.configure(bg="#09090b")
        dlg.transient(self.root)
        dlg.resizable(True, True)

        cfg = load_config()
        geo = cfg.get("builder_scan_names", "860x560")
        dlg.geometry(geo)
        dlg.minsize(700, 420)

        def on_close():
            save_config({"builder_scan_names": dlg.geometry()})
            dlg.destroy()
        dlg.protocol("WM_DELETE_WINDOW", on_close)

        # Header
        hdr = tk.Frame(dlg, bg="#18181b", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🔍 Scan Names", fg="#ffffff", bg="#18181b",
                 font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=16)
        hdr_count_lbl = tk.Label(hdr, text=f"{len(candidates)} ứng viên tìm được", fg="#a1a1aa", bg="#18181b",
                                 font=("Arial", 9))
        hdr_count_lbl.pack(side=tk.LEFT)

        # Re-scan button
        def rerun():
            on_close()
            self.open_scan_names_dialog()

        tk.Button(hdr, text="🔄 Quét lại", bg="#3f3f46", fg="#ffffff", relief="flat",
                  borderwidth=0, padx=10, pady=4, font=("Arial", 8), cursor="hand2",
                  command=rerun).pack(side=tk.RIGHT, padx=16)

        if not candidates:
            tk.Label(dlg, text="Không tìm thấy tên nào mới trong văn bản.\n(Tất cả các tên có thể đã có trong name.cfg).",
                     fg="#ef4444", bg="#09090b", font=("Arial", 10)).pack(pady=40)
            tk.Button(dlg, text="Đóng", command=on_close, bg="#27272a", fg="white",
                      relief="flat", borderwidth=0, padx=16, pady=6).pack()
            return

        # Filter bar
        filter_frame = tk.Frame(dlg, bg="#18181b", padx=16, pady=6)
        filter_frame.pack(fill=tk.X)
        tk.Label(filter_frame, text="Lọc:", fg="#a1a1aa", bg="#18181b", font=("Arial", 9)).pack(side=tk.LEFT)

        type_filter_var = tk.StringVar(value="TẤT CẢ")
        type_options = ["TẤT CẢ", "PERSON", "SECT", "PLACE", "SKILL", "ITEM", "UNKNOWN"]
        type_combo = ttk.Combobox(filter_frame, textvariable=type_filter_var,
                                  values=type_options, state="readonly", width=12, font=("Arial", 9))
        type_combo.pack(side=tk.LEFT, padx=(4, 12))

        min_conf_var = tk.IntVar(value=0)
        tk.Label(filter_frame, text="Conf ≥", fg="#a1a1aa", bg="#18181b", font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Spinbox(filter_frame, from_=0, to=99, textvariable=min_conf_var, width=4,
                   bg="#27272a", fg="white", insertbackground="white", relief="flat",
                   font=("Arial", 9)).pack(side=tk.LEFT, padx=(2, 0))
        tk.Label(filter_frame, text="%", fg="#a1a1aa", bg="#18181b", font=("Arial", 9)).pack(side=tk.LEFT, padx=(2, 12))

        # Column headers
        col_hdr = tk.Frame(dlg, bg="#27272a")
        col_hdr.pack(fill=tk.X, padx=12, pady=(6, 0))
        for text_label, w in [("Tiếng Trung", 14), ("Loại", 9), ("Xuất hiện", 8), ("Conf", 6),
                              ("Hán-Việt đề xuất (có thể sửa)", 0), ("", 14)]:
            anchor = "w" if w == 0 else "center"
            expand = w == 0
            tk.Label(col_hdr, text=text_label, fg="#71717a", bg="#27272a", font=("Arial", 8, "bold"),
                     width=w if w else None, anchor=anchor).pack(
                side=tk.LEFT, padx=4, pady=3, fill=tk.X if expand else None, expand=expand)

        # Scrollable list
        list_outer = tk.Frame(dlg, bg="#09090b")
        list_outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(2, 0))

        canvas = tk.Canvas(list_outer, bg="#09090b", highlightthickness=0)
        scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg="#09090b")
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        dlg.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Status bar
        tk.Frame(dlg, bg="#27272a", height=1).pack(fill=tk.X, padx=12, pady=(6, 0))
        status_var = tk.StringVar(value="")
        tk.Label(dlg, textvariable=status_var, fg="#10b981", bg="#09090b",
                 font=("Arial", 8)).pack(anchor="w", padx=16, pady=4)

        ignored: set = set()
        row_widgets: list = []  # list of (frame, cn)

        type_badge_colors = {
            'PERSON': '#1d4ed8', 'SECT': '#7c3aed', 'PLACE': '#065f46',
            'SKILL': '#b45309', 'ITEM': '#9f1239', 'UNKNOWN': '#3f3f46',
        }

        MAX_DISPLAY = 150

        def build_list(filter_type="TẤT CẢ", min_conf=0):
            for w in inner.winfo_children():
                w.destroy()
            row_widgets.clear()

            matching = [
                c for c in candidates
                if c['cn'] not in ignored
                and (filter_type == "TẤT CẢ" or c['type'] == filter_type)
                and (c['confidence'] * 100 >= min_conf)
            ]

            shown = 0
            for i, c in enumerate(matching[:MAX_DISPLAY]):
                row_bg = "#18181b" if shown % 2 == 0 else "#1c1c1f"
                row = tk.Frame(inner, bg=row_bg)
                row.pack(fill=tk.X, pady=1)
                row_widgets.append((row, c['cn']))

                # CN label (clickable to show context)
                cn_lbl = tk.Label(row, text=c['cn'], fg="#ffffff", bg=row_bg,
                                  font=("Consolas", 11, "bold"), width=14, cursor="hand2")
                cn_lbl.pack(side=tk.LEFT, padx=(8, 4), pady=4)

                def show_ctx(ev, cand=c):
                    ctxs = cand['contexts']
                    if ctxs:
                        messagebox.showinfo(
                            f"Ngữ cảnh: {cand['cn']}",
                            "\n\n".join(ctxs) or "Không có ngữ cảnh mẫu.",
                            parent=dlg
                        )
                cn_lbl.bind("<Button-1>", show_ctx)

                # Type badge
                badge_bg = type_badge_colors.get(c['type'], '#3f3f46')
                tk.Label(row, text=c['type'], fg="white", bg=badge_bg,
                         font=("Arial", 7, "bold"), width=9, padx=4, pady=1).pack(
                    side=tk.LEFT, padx=4, pady=6)

                # Count
                tk.Label(row, text=str(c['count']), fg="#10b981", bg=row_bg,
                         font=("Arial", 9), width=8).pack(side=tk.LEFT, padx=4)

                # Confidence
                conf_pct = int(c['confidence'] * 100)
                conf_fg = "#10b981" if conf_pct >= 60 else "#f59e0b" if conf_pct >= 30 else "#ef4444"
                tk.Label(row, text=f"{conf_pct}%", fg=conf_fg, bg=row_bg,
                         font=("Arial", 9, "bold"), width=6).pack(side=tk.LEFT, padx=4)

                # Editable VI suggestion
                vi_var = tk.StringVar(value=c['suggested_vi'])
                vi_entry = tk.Entry(row, textvariable=vi_var, bg=row_bg, fg="#e4e4e7",
                                    insertbackground="white", font=("Arial", 10), relief="flat",
                                    highlightthickness=1, highlightbackground="#3f3f46",
                                    highlightcolor="#7c3aed")
                vi_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=6)

                # Ignore button (fast: removes just this row)
                def do_ignore(target_row=row, cn=c['cn']):
                    ignored.add(cn)
                    target_row.destroy()
                    for idx, (r, name) in enumerate(row_widgets):
                        if name == cn:
                            row_widgets.pop(idx)
                            break
                    status_var.set(f"Đã bỏ qua: {cn}")

                tk.Button(row, text="Bỏ qua", bg="#27272a", fg="#a1a1aa", relief="flat",
                          borderwidth=0, padx=6, pady=3, font=("Arial", 8), cursor="hand2",
                          command=do_ignore).pack(side=tk.RIGHT, padx=2, pady=4)

                # Add button (fast: adds and removes just this row)
                def do_add(target_row=row, cn=c['cn'], vi_v=vi_var):
                    vi_text = vi_v.get().strip()
                    if not vi_text:
                        messagebox.showwarning("Chú ý", "Vui lòng nhập tên tiếng Việt!", parent=dlg)
                        return
                    self._add_name_to_cfg(cn, vi_text)
                    ignored.add(cn)
                    target_row.destroy()
                    for idx, (r, name) in enumerate(row_widgets):
                        if name == cn:
                            row_widgets.pop(idx)
                            break
                    status_var.set(f"✅ Đã thêm: {cn} = {vi_text}")

                tk.Button(row, text="Thêm", bg="#059669", fg="white", relief="flat",
                          borderwidth=0, padx=10, pady=3, font=("Arial", 8, "bold"),
                          cursor="hand2", command=do_add).pack(side=tk.RIGHT, padx=2, pady=4)

                shown += 1

            if shown == 0:
                tk.Label(inner, text="Không có ứng viên nào khớp bộ lọc.",
                         fg="#71717a", bg="#09090b", font=("Arial", 9)).pack(pady=16)
            elif len(matching) > MAX_DISPLAY:
                status_var.set(f"Hiển thị {MAX_DISPLAY}/{len(matching)} ứng viên hàng đầu (dùng bộ lọc để thu hẹp)")

        def apply_filter(event=None):
            build_list(type_filter_var.get(), min_conf_var.get())

        type_combo.bind("<<ComboboxSelected>>", apply_filter)
        min_conf_var.trace_add("write", lambda *_: apply_filter())

        build_list()

        # Bottom bar: Add All Visible
        tk.Frame(dlg, bg="#27272a", height=1).pack(fill=tk.X, padx=12)
        bot = tk.Frame(dlg, bg="#09090b", pady=8)
        bot.pack(fill=tk.X, padx=12)

        def add_all_visible():
            added = 0
            for _row, _cn in list(row_widgets):
                for child in _row.winfo_children():
                    if isinstance(child, tk.Entry):
                        vi_text = child.get().strip()
                        if vi_text and _cn not in ignored:
                            self._add_name_to_cfg(_cn, vi_text)
                            ignored.add(_cn)
                            added += 1
                        break
            build_list(type_filter_var.get(), min_conf_var.get())
            status_var.set(f"✅ Đã thêm {added} tên vào name.cfg")

        tk.Button(bot, text="Đóng", bg="#27272a", fg="#a1a1aa", activebackground="#3f3f46",
                  relief="flat", borderwidth=0, padx=16, pady=6, font=("Arial", 9),
                  cursor="hand2", command=on_close).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(bot, text="✅ Thêm tất cả đang hiển thị", bg="#7c3aed", fg="white",
                  activebackground="#6d28d9", relief="flat", borderwidth=0,
                  padx=16, pady=6, font=("Arial", 9, "bold"), cursor="hand2",
                  command=add_all_visible).pack(side=tk.RIGHT)


    def _add_name_to_cfg(self, cn: str, vi: str):
        """Add/update a name entry to name.cfg — reuses ReviewWindow.save_name_to_cfg logic."""
        if getattr(sys, 'frozen', False):
            cfg_dir = os.path.dirname(sys.executable)
        else:
            cfg_dir = BASE_DIR
        cfg_path = os.path.join(cfg_dir, "name.cfg")
        cn = unicodedata.normalize("NFC", cn.strip())
        vi = unicodedata.normalize("NFC", vi.strip())

        try:
            lines = []
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, _ = stripped.split("=", 1)
                    if k.strip() == cn:
                        lines[i] = f"{cn}={vi}\n"
                        found = True
                        break
            if not found:
                if lines and not lines[-1].endswith("\n"):
                    lines.append("\n")
                lines.append(f"{cn}={vi}\n")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể ghi name.cfg:\n{e}")

    def start_thread(self):

        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        title = self.ent_title.get().strip()
        content = self.txt_area.get(1.0, tk.END).strip()

        if not title or not content:
            messagebox.showwarning("Chú ý", "Vui lòng nhập tiêu đề và nội dung!")
            return

        slug = slugify_vn(title)
        if not slug:
            messagebox.showwarning("Chú ý", "Tiêu đề không hợp lệ, không thể tạo slug!")
            return

        self.btn_run.config(state="disabled")
        self.btn_clear.pack_forget()
        self.lbl_status.config(text=f"Slug: {slug} — Đang xử lý dữ liệu...", fg="#3b82f6")

        lines = [l.strip() for l in content.split("\n") if l.strip()]

        name_dict = self.load_name_config()
        sorted_names = sorted(name_dict.keys(), key=len, reverse=True)

        processed_lines = []
        for line in lines:
            replaced_line = line
            for cn in sorted_names:
                if cn in replaced_line:
                    replaced_line = replaced_line.replace(cn, name_dict[cn])
            processed_lines.append((line, replaced_line))

        chunks = []
        cur_g, cur_l = [], 0
        for orig_line, rep_line in processed_lines:
            if cur_l + len(rep_line) < CHUNK_LIMIT:
                cur_g.append((orig_line, rep_line))
                cur_l += len(rep_line)
            else:
                chunks.append(cur_g)
                cur_g, cur_l = [(orig_line, rep_line)], len(rep_line)
        if cur_g:
            chunks.append(cur_g)

        # Mảng để lưu trữ dữ liệu truyền sang màn hình Review
        final_cn_lines = []
        final_vi_lines = []

        for i, group in enumerate(chunks):
            self.lbl_status.config(text=f"Đang dịch đợt {i+1}/{len(chunks)}...")
            input_text = "\n".join([rep for _, rep in group])
            vi_res = self.translate_api(input_text)
            
            if not vi_res:
                time.sleep(3)
                vi_res = self.translate_api(input_text) or ("[Lỗi]\n" * len(group))

            vi_res = unicodedata.normalize('NFC', vi_res)
            vi_lines = vi_res.split("\n")
            vi_names = list(name_dict.values())
            
            name_words_set = set()
            for n in vi_names:
                for w in n.split():
                    name_words_set.add(w)
            
            for j in range(len(group)):
                orig_cn, rep_cn = group[j]
                vi = vi_lines[j] if j < len(vi_lines) else ""
                
                # Loại bỏ dấu cách kép do từ không có kết quả dịch
                vi = re.sub(r'  +', ' ', vi).strip()
                
                # Hạ chữ hoa (nếu có) của từ ngay sau name (do API tự viết hoa)
                for name in vi_names:
                    if name in vi:
                        pattern = re.compile(re.escape(name) + r'(\s+)([\w]+)', re.UNICODE)
                        def replacer(match, n=name):
                            space = match.group(1)
                            word = match.group(2)
                            if word.istitle() and word not in name_words_set:
                                return n + space + word.lower()
                            return match.group(0)
                        vi = pattern.sub(replacer, vi)
                
                # Chỉ lấy nguyên bản đoạn dịch và đẩy vào mảng, không tự ép viết hoa nữa
                final_cn_lines.append(orig_cn)
                final_vi_lines.append(vi)
                
            time.sleep(DELAY)

        self.lbl_status.config(text="Hoàn tất dịch API. Đang mở cửa sổ Review...", fg="#f59e0b")
        
        # Gọi UI Review trong main thread
        self.root.after(0, lambda: ReviewWindow(self.root, title, slug, final_cn_lines, final_vi_lines, self))

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = TranslatorGUI(root)
    root.mainloop()