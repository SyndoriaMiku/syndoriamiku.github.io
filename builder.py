import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import requests, json, os, sys, base64, datetime, time, threading
import unicodedata, re
from tkinterdnd2 import TkinterDnD, DND_FILES

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
        self.top.geometry("900x700")
        self.top.configure(bg="#09090b")
        
        self.title = title
        self.slug = slug
        self.cn_lines = cn_lines
        self.vi_lines = vi_lines
        self.app = app_instance

        self.setup_ui()
        self.load_content()

    def setup_ui(self):
        ctrl_frame = tk.Frame(self.top, bg="#09090b")
        ctrl_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(ctrl_frame, text="Bôi đen chữ bên dưới ➡️ Click chuột phải để Thêm Name", fg="#a1a1aa", bg="#09090b").pack(side="left")
        
        btn_save = tk.Button(ctrl_frame, text="💾 Lưu vào data.json", command=self.save_data, bg="#10b981", fg="white", borderwidth=0, padx=15)
        btn_save.pack(side="right")

        self.text_editor = scrolledtext.ScrolledText(self.top, wrap=tk.WORD, bg="#18181b", fg="#e4e4e7", font=("Consolas", 11), borderwidth=0)
        self.text_editor.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.text_editor.tag_config("cn", foreground="#71717a")
        self.text_editor.tag_config("vi", foreground="#ffffff")
        
        self.menu = tk.Menu(self.top, tearoff=0, bg="#27272a", fg="white", borderwidth=0)
        self.menu.add_command(label="Sửa lỗi & Thêm Name", command=self.prompt_add_name)
        
        self.text_editor.bind("<Button-3>", self.show_context_menu)

    def load_content(self):
        # Lưu lại vị trí cuộn chuột (scrollbar) hiện tại để khi update UI không bị giật lên đầu trang
        scroll_pos = self.text_editor.yview()
        
        self.text_editor.config(state=tk.NORMAL)
        self.text_editor.delete(1.0, tk.END)
        for i in range(len(self.cn_lines)):
            self.text_editor.insert(tk.END, f"{self.cn_lines[i]}\n", "cn")
            self.text_editor.insert(tk.END, f"{self.vi_lines[i]}\n\n", "vi")
        self.text_editor.config(state=tk.DISABLED)
        
        # Phục hồi vị trí cuộn
        self.text_editor.yview_moveto(scroll_pos[0])

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
        extracted_vi = ""
        # Nếu người dùng bôi đen nhầm cả thẻ HTML của API, tự động bóc tách
        match_tag = re.search(r"<i[^>]*t=['\"]([^'\"]+)['\"][^>]*>([^<]+)</i>", selected_text, re.IGNORECASE)
        if match_tag:
            selected_text = match_tag.group(1).strip() # Lấy tiếng Trung làm gốc
            extracted_vi = match_tag.group(2).strip()  # Lấy tiếng Việt làm từ sai

        # Check xem chuỗi bôi đen có chứa ký tự CJK (Tiếng Trung) không
        is_cn = any('\u4e00' <= char <= '\u9fff' for char in selected_text)

        dialog = tk.Toplevel(self.top)
        dialog.title("Sửa lỗi & Thêm Name Mới")
        dialog.geometry("420x350")
        dialog.configure(bg="#18181b")
        dialog.transient(self.top)
        dialog.grab_set()

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
        elif extracted_vi:
            ent_wrong.insert(0, extracted_vi)

        # 3. Ô Name đúng
        tk.Label(dialog, text="3. Sửa thành (Name đúng):", fg="#10b981", bg="#18181b", font=("Arial", 10, "bold")).pack(pady=(10,0), anchor="w", padx=20)
        ent_right = tk.Entry(dialog, bg="#27272a", fg="white", borderwidth=0, insertbackground="white")
        ent_right.pack(fill="x", padx=20, pady=5, ipady=5)

        def apply_name():
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

            import re
            
            # Kiểm tra xem có thẻ tag của cn_val do API trả về không
            has_tag = False
            if cn_val:
                pattern_tag_find = re.compile(r"<i[^>]*t=['\"]" + re.escape(cn_val) + r"['\"][^>]*>", re.IGNORECASE)
                for line in self.vi_lines:
                    if pattern_tag_find.search(line):
                        has_tag = True
                        break

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

            if not wrong_val and not has_tag:
                if not messagebox.askyesno("Xác nhận", "Bạn chưa nhập 'Cụm từ VN bị dịch sai' (Ô số 2) và hệ thống không thể tự động nhận diện.\n\nHệ thống sẽ lưu Name vào từ điển để áp dụng cho các chương sau, nhưng SẼ KHÔNG THỂ thay thế tự động trong đoạn text hiện tại.\n\nBạn có muốn tiếp tục?", parent=dialog):
                    return

            # Replace toàn bộ chữ sai thành chữ đúng trên mảng RAM (áp dụng cho TOÀN BỘ file truyện)
            for i in range(len(self.vi_lines)):
                # 1. Thay thế global nếu người dùng có nhập wrong_val
                if wrong_val:
                    # Dùng Regex để thay thế không phân biệt hoa thường (case-insensitive)
                    pattern_wrong = re.compile(re.escape(wrong_val), re.IGNORECASE)
                    self.vi_lines[i] = pattern_wrong.sub(right_val, self.vi_lines[i])

                # 2. Xóa và thay thế trực tiếp các thẻ HTML chứa cn_val thành Name đúng
                if cn_val:
                    pattern_tag_replace = re.compile(r"<i[^>]*t=['\"]" + re.escape(cn_val) + r"['\"][^>]*>[^<]*</i>", re.IGNORECASE)
                    self.vi_lines[i] = pattern_tag_replace.sub(right_val, self.vi_lines[i])

            # Ghi Tiếng Trung = Name đúng vào file config
            if cn_val:
                self.save_name_to_cfg(cn_val, right_val)

            self.load_content() # Render lại giao diện ngay lập tức
            dialog.destroy()

        tk.Button(dialog, text="🚀 Lưu Name & Cập nhật toàn bộ", command=apply_name, bg="#3b82f6", fg="white", borderwidth=0).pack(pady=20, ipadx=10, ipady=5)

    def save_name_to_cfg(self, cn, vi):
        cfg_path = os.path.join(BASE_DIR, "name.cfg")
        with open(cfg_path, "a", encoding="utf-8") as f:
            f.write(f"\n{cn}={vi}")

    def save_data(self):
        output_dir = os.path.join(BASE_DIR, "stories", self.slug)
        os.makedirs(output_dir, exist_ok=True)
        
        story_data = {"title": self.title, "content": []}
        
        for i in range(len(self.cn_lines)):
            cn_nfc = unicodedata.normalize('NFC', self.cn_lines[i])
            vi_nfc = unicodedata.normalize('NFC', self.vi_lines[i])
            story_data["content"].append({
                "cn": base64.b64encode(cn_nfc.encode('utf-8')).decode('utf-8'),
                "vi": base64.b64encode(vi_nfc.encode('utf-8')).decode('utf-8')
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
        self.root.geometry("700x600")
        self.root.configure(bg="#09090b")

        # UI Components
        self.setup_ui()

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
            return res.text.strip() if res.status_code == 200 else None
        except: return None

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
            
            for j in range(len(group)):
                orig_cn, rep_cn = group[j]
                vi = vi_lines[j] if j < len(vi_lines) else ""
                
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