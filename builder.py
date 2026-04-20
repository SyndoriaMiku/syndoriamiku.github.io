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
    # Extra mapping for characters that unicodedata doesn't decompose well
    _vn_map = str.maketrans(
        "đĐ",
        "dD",
    )
    text = text.translate(_vn_map)
    # Normalize to NFD so accents become separate combining characters, then strip them
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)   # keep only alphanum, spaces, hyphens
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text

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
        # Hidden by default, shown after completion

        # Progress Label
        self.lbl_status = tk.Label(self.root, text="Sẵn sàng", fg="#71717a", bg="#09090b")
        self.lbl_status.pack(pady=5)

    def clear_all(self):
        """Clear all inputs and reset the UI."""
        self.ent_title.delete(0, tk.END)
        self.txt_area.delete(1.0, tk.END)
        self.lbl_status.config(text="Sẵn sàng", fg="#71717a")
        self.btn_clear.pack_forget()

    def handle_drop(self, event):
        """Handle files dropped onto the drop zone."""
        # Reset drop zone appearance
        self.drop_zone.config(bg="#18181b", fg="#71717a")
        # tkdnd wraps paths with spaces in {}, parse them
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
        """Load a .txt file into the text area and suggest the title."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.txt_area.delete(1.0, tk.END)
                self.txt_area.insert(tk.END, f.read())
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đọc file:\n{e}")
            return

        # Tự động gợi ý title từ tên file
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

        existing = next((item for item in catalog if item['slug'] == slug), None)
        now = datetime.datetime.now()
        if not existing:
            catalog.append({"title": title, "slug": slug, "date": now.strftime("%d/%m/%Y"), "timestamp": now.timestamp()})
        else:
            existing['date'] = now.strftime("%d/%m/%Y")
            existing['timestamp'] = now.timestamp()

        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=4)

    def translate_api(self, text):
        headers = {"Origin": "https://www.bilibili.com", "Referer": "https://www.bilibili.com/", "User-Agent": "Mozilla/5.0"}
        try:
            res = requests.post(API_URL, data={"sajax": "trans", "content": text}, headers=headers, timeout=45)
            return res.text.strip() if res.status_code == 200 else None
        except: return None

    def start_thread(self):
        # Chạy trong thread riêng để không bị treo UI
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

        output_dir = os.path.join(BASE_DIR, "stories", slug)
        os.makedirs(output_dir, exist_ok=True)

        lines = [l.strip() for l in content.split("\n") if l.strip()]
        story_data = {"title": title, "content": []}

        # Chunking
        chunks = []
        cur_g, cur_l = [], 0
        for line in lines:
            if cur_l + len(line) < CHUNK_LIMIT:
                cur_g.append(line)
                cur_l += len(line)
            else:
                chunks.append(cur_g)
                cur_g, cur_l = [line], len(line)
        chunks.append(cur_g)

        for i, group in enumerate(chunks):
            self.lbl_status.config(text=f"Đang dịch đợt {i+1}/{len(chunks)}...")
            input_text = "\n".join(group)
            vi_res = self.translate_api(input_text)
            
            if not vi_res:
                time.sleep(3)
                vi_res = self.translate_api(input_text) or ("[Lỗi]\n" * len(group))

            vi_lines = vi_res.split("\n")
            for j in range(len(group)):
                cn = group[j]
                vi = vi_lines[j] if j < len(vi_lines) else ""
                story_data["content"].append({
                    "cn": base64.b64encode(cn.encode('utf-8')).decode('utf-8'),
                    "vi": base64.b64encode(vi.encode('utf-8')).decode('utf-8')
                })
            time.sleep(DELAY)

        # Save files
        with open(os.path.join(output_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(story_data, f, ensure_ascii=False)

        if os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, "r", encoding="utf-8") as f_t, open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as f_i:
                f_i.write(f_t.read())

        self.update_catalog(story_data["title"], slug)
        self.lbl_status.config(text="✅ Hoàn thành!", fg="#10b981")
        self.btn_run.config(state="normal")
        self.btn_clear.pack(side="right", padx=5)
        messagebox.showinfo("Thành công", f"Đã dịch xong truyện: {slug}")

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = TranslatorGUI(root)
    root.mainloop()