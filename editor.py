import base64
import json
import os
import re
import unicodedata
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CATALOG_PATH = os.path.join(LIBRARY_DIR, "list.json")
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



def safe_decode_b64(value):
	try:
		raw = base64.b64decode(value)
		text = raw.decode("utf-8")
		return unicodedata.normalize('NFC', text)
	except Exception:
		return "[Loi giai ma]"


def slugify_vn(text):
	"""Convert a Vietnamese (or any) title into a URL-friendly slug."""
	_vn_map = str.maketrans("đĐ", "dD")
	text = text.translate(_vn_map)
	text = unicodedata.normalize("NFD", text)
	text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
	text = text.lower()
	text = re.sub(r"[^a-z0-9\s-]", "", text)  # keep only alphanum, spaces, hyphens
	text = re.sub(r"[\s-]+", "-", text).strip("-")
	return text


def setup_text_shortcuts(widget):
	def select_all(event):
		widget.tag_add("sel", "1.0", "end")
		return "break"

	def copy(event):
		try:
			selected = widget.get("sel.first", "sel.last")
			widget.clipboard_clear()
			widget.clipboard_append(selected)
		except tk.TclError:
			pass
		return "break"

	def cut(event):
		try:
			selected = widget.get("sel.first", "sel.last")
			widget.clipboard_clear()
			widget.clipboard_append(selected)
			widget.delete("sel.first", "sel.last")
		except tk.TclError:
			pass
		return "break"

	def paste(event):
		try:
			text = widget.clipboard_get()
			if widget.tag_ranges("sel"):
				widget.delete("sel.first", "sel.last")
			widget.insert(tk.INSERT, text)
		except tk.TclError:
			pass
		return "break"

	def undo(event):
		try:
			widget.edit_undo()
		except tk.TclError:
			pass
		return "break"

	def redo(event):
		try:
			widget.edit_redo()
		except tk.TclError:
			pass
		return "break"

	widget.bind("<Control-a>", select_all)
	widget.bind("<Control-A>", select_all)
	widget.bind("<Control-c>", copy)
	widget.bind("<Control-C>", copy)
	widget.bind("<Control-x>", cut)
	widget.bind("<Control-X>", cut)
	widget.bind("<Control-v>", paste)
	widget.bind("<Control-V>", paste)
	widget.bind("<Control-z>", undo)
	widget.bind("<Control-Z>", undo)
	widget.bind("<Control-y>", redo)
	widget.bind("<Control-Y>", redo)


def setup_entry_shortcuts(widget):
	def select_all(event):
		widget.select_range(0, tk.END)
		widget.icursor(tk.END)
		return "break"

	def copy(event):
		if widget.select_present():
			widget.clipboard_clear()
			widget.clipboard_append(widget.selection_get())
		return "break"

	def cut(event):
		if widget.select_present():
			widget.clipboard_clear()
			widget.clipboard_append(widget.selection_get())
			first = widget.index("sel.first")
			last = widget.index("sel.last")
			widget.delete(first, last)
		return "break"

	def paste(event):
		try:
			text = widget.clipboard_get()
			if widget.select_present():
				first = widget.index("sel.first")
				last = widget.index("sel.last")
				widget.delete(first, last)
			widget.insert(tk.INSERT, text)
		except tk.TclError:
			pass
		return "break"

	widget.bind("<Control-a>", select_all)
	widget.bind("<Control-A>", select_all)
	widget.bind("<Control-c>", copy)
	widget.bind("<Control-C>", copy)
	widget.bind("<Control-x>", cut)
	widget.bind("<Control-X>", cut)
	widget.bind("<Control-v>", paste)
	widget.bind("<Control-V>", paste)


class ChapterEditorApp:
	def __init__(self, root):
		self.root = root
		self.root.title("Trình Chỉnh Sửa Chapter & Quản Lý Thư Viện")
		self.root.configure(bg="#09090b")

		self.loaded_json = None
		self.story_options = []
		self._resize_timer = None

		# Restore saved geometry or use default
		cfg = load_config()
		geo = cfg.get("editor_main", "1300x750")
		self.root.geometry(geo)

		self.setup_ui()
		self.load_story_list()

		# Save geometry on resize (debounced)
		self.root.bind("<Configure>", self._on_root_configure)

	def _on_root_configure(self, event=None):
		if event and event.widget is not self.root:
			return
		if self._resize_timer:
			self.root.after_cancel(self._resize_timer)
		self._resize_timer = self.root.after(600, self._save_root_geometry)

	def _save_root_geometry(self):
		geo = self.root.geometry()
		save_config({"editor_main": geo})


	def setup_ui(self):
		header = tk.Frame(self.root, bg="#09090b")
		header.pack(fill="x", padx=20, pady=(20, 10))

		tk.Label(
			header,
			text="📚 TRÌNH CHỈNH SỬA CHAPTER & QUẢN LÝ THƯ VIỆN",
			fg="#ffffff",
			bg="#09090b",
			font=("Arial", 14, "bold"),
		).pack(side="left")

		container = tk.Frame(self.root, bg="#09090b")
		container.pack(fill="both", expand=True, padx=20, pady=10)

		left = tk.Frame(container, bg="#18181b", bd=1, relief="solid")
		left.pack(side="left", fill="both", expand=True, padx=(0, 10))

		right = tk.Frame(container, bg="#18181b", bd=1, relief="solid")
		right.pack(side="left", fill="both", expand=True, padx=(10, 0))

		self.build_left(left)
		self.build_right(right)

	def build_left(self, parent):
		tk.Label(
			parent,
			text="📝 Text Editor (Chỉnh sửa nội dung & Lưu thư viện)",
			fg="#ffffff",
			bg="#18181b",
			font=("Arial", 11, "bold"),
		).pack(anchor="w", padx=16, pady=(14, 10))

		form = tk.Frame(parent, bg="#18181b")
		form.pack(fill="both", expand=True, padx=16)

		# Story selection row with "Them Truyen" button
		story_frame = tk.Frame(form, bg="#18181b")
		story_frame.pack(fill="x", pady=(0, 12))

		tk.Label(
			story_frame,
			text="Chọn Truyện:",
			fg="#a1a1aa",
			bg="#18181b",
		).pack(anchor="w")

		self.story_combo = ttk.Combobox(story_frame, values=self.story_options, font=("Arial", 10))
		self.story_combo.pack(side="left", fill="x", expand=True, pady=(4, 0))
		self.story_combo.bind("<<ComboboxSelected>>", self.on_story_selected)

		tk.Button(
			story_frame,
			text="➕ Thêm Truyện Mới",
			bg="#10b981",
			fg="#ffffff",
			command=self.add_new_story,
			borderwidth=0,
			padx=10,
			pady=4,
			font=("Arial", 9, "bold"),
			cursor="hand2"
		).pack(side="right", padx=(10, 0), pady=(4, 0))

		# Chapter ID and Title row
		chap_select_frame = tk.Frame(form, bg="#18181b")
		chap_select_frame.pack(fill="x", pady=(0, 6))

		tk.Label(
			chap_select_frame,
			text="Chọn Chương để chỉnh sửa:",
			fg="#a1a1aa",
			bg="#18181b",
		).pack(anchor="w")

		chap_select_inner = tk.Frame(chap_select_frame, bg="#18181b")
		chap_select_inner.pack(fill="x", pady=(4, 0))

		self.chap_select_combo = ttk.Combobox(chap_select_inner, font=("Arial", 10), state="readonly")
		self.chap_select_combo.pack(side="left", fill="x", expand=True)

		tk.Button(
			chap_select_inner,
			text="✏️ Load chương",
			bg="#3b82f6",
			fg="#ffffff",
			command=self.load_chapter_for_edit,
			borderwidth=0,
			padx=10,
			pady=3,
			font=("Arial", 9, "bold"),
			cursor="hand2"
		).pack(side="right", padx=(10, 0))

		# Chapter ID and Title row
		chap_meta_frame = tk.Frame(form, bg="#18181b")
		chap_meta_frame.pack(fill="x", pady=(0, 12))


		# Left side: Chapter ID (slug)
		chap_id_frame = tk.Frame(chap_meta_frame, bg="#18181b")
		chap_id_frame.pack(side="left", fill="x", expand=True, padx=(0, 6))

		tk.Label(
			chap_id_frame,
			text="Chapter ID (Auto 6 chữ số, VD: 000001):",
			fg="#a1a1aa",
			bg="#18181b",
		).pack(anchor="w")

		self.chap_entry = tk.Entry(chap_id_frame, bg="#09090b", fg="#ffffff", insertbackground="white", font=("Arial", 10))
		self.chap_entry.pack(fill="x", pady=(4, 0), ipady=4)
		setup_entry_shortcuts(self.chap_entry)

		# Right side: Chapter Title (Tên chương)
		chap_title_frame = tk.Frame(chap_meta_frame, bg="#18181b")
		chap_title_frame.pack(side="left", fill="x", expand=True, padx=(6, 0))

		tk.Label(
			chap_title_frame,
			text="Tên Chương (VD: Chương 1: Sự khởi đầu):",
			fg="#a1a1aa",
			bg="#18181b",
		).pack(anchor="w")

		self.chap_title_entry = tk.Entry(chap_title_frame, bg="#09090b", fg="#ffffff", insertbackground="white", font=("Arial", 10))
		self.chap_title_entry.pack(fill="x", pady=(4, 0), ipady=4)
		setup_entry_shortcuts(self.chap_title_entry)

		# Vietnamese content
		tk.Label(
			form,
			text="Nội dung Tiếng Việt:",
			fg="#a1a1aa",
			bg="#18181b",
		).pack(anchor="w")

		self.content_text = scrolledtext.ScrolledText(
			form,
			height=18,
			bg="#09090b",
			fg="#e4e4e7",
			insertbackground="white",
			font=("Consolas", 11),
			wrap=tk.WORD,
			undo=True
		)
		self.content_text.pack(fill="both", expand=True, pady=(4, 12))
		setup_text_shortcuts(self.content_text)

		btns = tk.Frame(form, bg="#18181b")
		btns.pack(fill="x", pady=(0, 16))

		tk.Button(
			btns,
			text="💾 Lưu trực tiếp vào Thư Viện",
			bg="#10b981",
			fg="#ffffff",
			command=self.save_chapter,
			borderwidth=0,
			padx=20,
			pady=8,
			font=("Arial", 10, "bold"),
			cursor="hand2"
		).pack(side="left")



	def build_right(self, parent):
		tk.Label(
			parent,
			text="📂 Giải mã JSON (Từ stories/ hoặc data.json cũ)",
			fg="#ffffff",
			bg="#18181b",
			font=("Arial", 11, "bold"),
		).pack(anchor="w", padx=16, pady=(14, 10))

		tk.Label(
			parent,
			text="Chọn file data.json của chương để trích xuất tiếng Việt đã dịch.",
			fg="#a1a1aa",
			bg="#18181b",
		).pack(anchor="w", padx=16)

		tk.Button(
			parent,
			text="📁 Chọn file JSON",
			bg="#3b82f6",
			fg="#ffffff",
			command=self.pick_json,
			borderwidth=0,
			padx=16,
			pady=6,
			font=("Arial", 10),
			cursor="hand2"
		).pack(anchor="w", padx=16, pady=(10, 6))

		tk.Button(
			parent,
			text="📥 Thêm toàn bộ Tiếng Việt sang Editor ←",
			bg="#10b981",
			fg="#ffffff",
			command=self.process_json,
			borderwidth=0,
			padx=16,
			pady=6,
			font=("Arial", 10, "bold"),
			cursor="hand2"
		).pack(anchor="w", padx=16, pady=(0, 6))

		tk.Button(
			parent,
			text="✂️ Chuyển phần bôi đen sang Editor ←",
			bg="#f59e0b",
			fg="#ffffff",
			command=self.move_selected_text,
			borderwidth=0,
			padx=16,
			pady=6,
			font=("Arial", 10, "bold"),
			cursor="hand2"
		).pack(anchor="w", padx=16, pady=(0, 6))

		tk.Button(
			parent,
			text="🔪 Phân Chương Tự Động",
			bg="#8b5cf6",
			fg="#ffffff",
			command=self.open_split_chapters_dialog,
			borderwidth=0,
			padx=16,
			pady=6,
			font=("Arial", 10, "bold"),
			cursor="hand2"
		).pack(anchor="w", padx=16, pady=(0, 10))


		# Status Label for loaded JSON info
		self.temp_status = tk.Label(
			parent,
			text="Trạng thái: Chưa chọn file...",
			fg="#a1a1aa",
			bg="#18181b",
			anchor="w",
			justify="left",
			font=("Arial", 9)
		)
		self.temp_status.pack(anchor="w", padx=16, pady=(0, 10))

		# Sleek search bar (hidden by default)
		self.search_frame = tk.Frame(parent, bg="#27272a", bd=1, relief="solid")
		
		# Elements inside search bar
		tk.Label(self.search_frame, text="🔍 Tìm:", fg="#ffffff", bg="#27272a", font=("Arial", 9, "bold")).pack(side="left", padx=(8, 4))
		
		self.search_entry = tk.Entry(self.search_frame, bg="#09090b", fg="#ffffff", insertbackground="white", font=("Arial", 9))
		self.search_entry.pack(side="left", fill="x", expand=True, pady=4, padx=4)
		setup_entry_shortcuts(self.search_entry)
		
		self.regex_var = tk.BooleanVar(value=False)
		self.regex_check = tk.Checkbutton(
			self.search_frame,
			text="Regex",
			variable=self.regex_var,
			bg="#27272a",
			fg="#ffffff",
			selectcolor="#09090b",
			activebackground="#27272a",
			activeforeground="#ffffff",
			font=("Arial", 8),
			command=self.perform_search
		)
		self.regex_check.pack(side="left", padx=4)
		
		self.search_status = tk.Label(self.search_frame, text="0/0", fg="#a1a1aa", bg="#27272a", font=("Arial", 8))
		self.search_status.pack(side="left", padx=4)
		
		tk.Button(
			self.search_frame,
			text="←",
			bg="#3f3f46",
			fg="#ffffff",
			command=self.find_prev,
			borderwidth=0,
			padx=6,
			font=("Arial", 8),
			cursor="hand2"
		).pack(side="left", padx=2)
		
		tk.Button(
			self.search_frame,
			text="→",
			bg="#3f3f46",
			fg="#ffffff",
			command=self.find_next,
			borderwidth=0,
			padx=6,
			font=("Arial", 8),
			cursor="hand2"
		).pack(side="left", padx=2)
		
		tk.Button(
			self.search_frame,
			text="⬆️ Chọn Lên",
			bg="#8b5cf6",
			fg="#ffffff",
			command=self.select_above_match,
			borderwidth=0,
			padx=8,
			font=("Arial", 8, "bold"),
			cursor="hand2"
		).pack(side="left", padx=(2, 4))
		
		tk.Button(
			self.search_frame,
			text="✕",
			bg="#ef4444",
			fg="#ffffff",
			command=self.hide_search_dialog,
			borderwidth=0,
			padx=8,
			font=("Arial", 8, "bold"),
			cursor="hand2"
		).pack(side="left", padx=(4, 8))

		# Temp text window
		self.temp_text = scrolledtext.ScrolledText(
			parent,
			height=20,
			bg="#09090b",
			fg="#e4e4e7",
			insertbackground="white",
			font=("Consolas", 10),
			wrap=tk.WORD,
			undo=True
		)
		self.temp_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
		setup_text_shortcuts(self.temp_text)
		
		# Configure match tags
		self.temp_text.tag_configure("match", background="#b45309", foreground="#ffffff")
		self.temp_text.tag_configure("active_match", background="#10b981", foreground="#ffffff")
		
		# Binds
		self.temp_text.bind("<Control-f>", self.show_search_dialog)
		self.temp_text.bind("<Control-F>", self.show_search_dialog)
		
		self.search_entry.bind("<KeyRelease>", self.schedule_search)
		self.search_entry.bind("<Return>", self.find_next)
		self.search_entry.bind("<Shift-Return>", self.find_prev)
		self.search_entry.bind("<Escape>", self.hide_search_dialog)

	def load_story_list(self):
		self.story_options = []
		os.makedirs(LIBRARY_DIR, exist_ok=True)
		
		# Auto-migrate list.json from stories/ to library/ if not exists
		if not os.path.exists(CATALOG_PATH):
			old_catalog = os.path.join(BASE_DIR, "stories", "list.json")
			if os.path.exists(old_catalog):
				try:
					import shutil
					shutil.copy2(old_catalog, CATALOG_PATH)
				except Exception:
					pass

		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					data = json.load(f)
				for item in data:
					slug = item.get("slug")
					title = item.get("title", "")
					if slug:
						self.story_options.append(f"{slug} | {title}")
			except Exception:
				pass

		self.story_combo["values"] = self.story_options

	def get_next_story_id(self):
		catalog = []
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					catalog = json.load(f)
			except Exception:
				pass
		
		max_id = 0
		for item in catalog:
			slug = item.get("slug", "")
			if slug.isdigit():
				val = int(slug)
				if val > max_id:
					max_id = val
		
		next_id = max_id + 1
		return f"{next_id:04d}"

	def get_next_chapter_id(self, story_slug):
		if not story_slug:
			return "000001"

		catalog = []
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					catalog = json.load(f)
			except Exception:
				pass

		story = next((item for item in catalog if item.get('slug') == story_slug), None)
		if not story or 'chapters' not in story or not story['chapters']:
			return "000001"

		max_id = 0
		for chap in story['chapters']:
			chap_id = chap.get("id", "")
			if chap_id.isdigit():
				val = int(chap_id)
				if val > max_id:
					max_id = val

		next_id = max_id + 1
		return f"{next_id:06d}"

	def on_story_selected(self, event=None):
		story_value = self.story_combo.get().strip()
		if not story_value:
			return

		if "|" in story_value:
			story_slug, _ = story_value.split("|", 1)
			story_slug = story_slug.strip()
		else:
			story_slug = slugify_vn(story_value)

		next_chap_id = self.get_next_chapter_id(story_slug)
		self.chap_entry.delete(0, tk.END)
		self.chap_entry.insert(0, next_chap_id)

		# Populate chapter select combobox
		self._refresh_chap_select(story_slug)

	def _refresh_chap_select(self, story_slug):
		"""Load chapter list for the selected story into chap_select_combo."""
		catalog = []
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					catalog = json.load(f)
			except Exception:
				pass

		story = next((item for item in catalog if item.get("slug") == story_slug), None)
		chap_options = []
		if story:
			for chap in story.get("chapters", []):
				cid = chap.get("id", "")
				cname = chap.get("name", "")
				chap_options.append(f"{cid} | {cname}")

		self.chap_select_combo["values"] = chap_options
		self.chap_select_combo.set("")


	def load_chapter_for_edit(self):
		"""Load a chapter from library into the editor for editing."""
		story_value = self.story_combo.get().strip()
		if not story_value:
			messagebox.showwarning("Chú ý", "Vui lòng chọn Truyện trước!")
			return

		chap_value = self.chap_select_combo.get().strip()
		if not chap_value:
			messagebox.showwarning("Chú ý", "Vui lòng chọn Chương muốn sửa!")
			return

		if "|" in story_value:
			story_slug = story_value.split("|", 1)[0].strip()
		else:
			story_slug = slugify_vn(story_value)

		if "|" in chap_value:
			chap_slug = chap_value.split("|", 1)[0].strip()
		else:
			chap_slug = chap_value

		data_path = os.path.join(LIBRARY_DIR, story_slug, chap_slug, "data.json")
		if not os.path.exists(data_path):
			messagebox.showerror("Lỗi", f"Không tìm thấy file:\n{data_path}")
			return

		try:
			with open(data_path, "r", encoding="utf-8") as f:
				chapter_json = json.load(f)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể đọc file data.json:\n{e}")
			return

		# Decode VI paragraphs
		vi_paragraphs = []
		for item in chapter_json.get("content", []):
			vi = item.get("vi")
			if vi:
				vi_paragraphs.append(safe_decode_b64(vi))

		chap_title = chapter_json.get("chapter_title", "")

		# Fill editor
		self.chap_entry.delete(0, tk.END)
		self.chap_entry.insert(0, chap_slug)
		self.chap_title_entry.delete(0, tk.END)
		if chap_title:
			self.chap_title_entry.insert(0, chap_title)
		self.content_text.delete("1.0", tk.END)
		self.content_text.insert("1.0", "\n\n".join(vi_paragraphs))

		messagebox.showinfo("Đã load", f"Đã load chương: {chap_value}\nChỉnh sửa xong bấm 'Lưu' để ghi đè.")

	def add_new_story(self):
		default_title = ""
		if self.loaded_json and "title" in self.loaded_json:
			default_title = self.loaded_json.get("title", "")

		dialog = tk.Toplevel(self.root)
		dialog.title("Thêm Truyện Mới")
		dialog.resizable(True, False)
		dialog.transient(self.root)
		dialog.grab_set()
		dialog.configure(bg="#18181b")

		# Header
		header_frame = tk.Frame(dialog, bg="#09090b", pady=12)
		header_frame.pack(fill=tk.X)
		tk.Label(
			header_frame,
			text="➕ Thêm Truyện Mới",
			fg="#ffffff",
			bg="#09090b",
			font=("Arial", 11, "bold"),
		).pack(padx=16, anchor="w")

		# Body
		body_frame = tk.Frame(dialog, bg="#18181b")
		body_frame.pack(fill=tk.X, padx=16, pady=(14, 0))

		tk.Label(
			body_frame,
			text="Tên hiển thị của truyện:",
			fg="#a1a1aa",
			bg="#18181b",
			font=("Arial", 9),
		).pack(anchor="w")

		entry_var = tk.StringVar(value=default_title)
		entry = tk.Entry(
			body_frame,
			textvariable=entry_var,
			bg="#09090b",
			fg="#ffffff",
			insertbackground="#ffffff",
			relief="flat",
			font=("Arial", 11),
			bd=0,
			highlightthickness=1,
			highlightbackground="#3f3f46",
			highlightcolor="#10b981",
		)
		entry.pack(fill=tk.X, pady=(6, 0), ipady=7)
		entry.select_range(0, tk.END)
		entry.focus_set()

		# Hint
		tk.Label(
			body_frame,
			text="ID 4 chữ số sẽ được tạo tự động.",
			fg="#52525b",
			bg="#18181b",
			font=("Arial", 8),
		).pack(anchor="w", pady=(4, 0))

		# Separator
		tk.Frame(dialog, bg="#27272a", height=1).pack(fill=tk.X, pady=(14, 0))

		# Buttons
		btn_frame = tk.Frame(dialog, bg="#18181b")
		btn_frame.pack(fill=tk.X, padx=16, pady=12)

		title_result = [None]

		def on_ok(event=None):
			title_result[0] = entry_var.get()
			save_config({"editor_add_story_dialog": dialog.geometry()})
			dialog.destroy()

		def on_cancel(event=None):
			save_config({"editor_add_story_dialog": dialog.geometry()})
			dialog.destroy()

		tk.Button(
			btn_frame,
			text="Hủy",
			bg="#27272a",
			fg="#a1a1aa",
			activebackground="#3f3f46",
			activeforeground="#ffffff",
			relief="flat",
			borderwidth=0,
			padx=18,
			pady=6,
			font=("Arial", 9),
			cursor="hand2",
			command=on_cancel,
		).pack(side=tk.RIGHT, padx=(6, 0))

		tk.Button(
			btn_frame,
			text="✅ Tạo Truyện",
			bg="#10b981",
			fg="#ffffff",
			activebackground="#059669",
			activeforeground="#ffffff",
			relief="flat",
			borderwidth=0,
			padx=18,
			pady=6,
			font=("Arial", 9, "bold"),
			cursor="hand2",
			command=on_ok,
		).pack(side=tk.RIGHT)

		entry.bind("<Return>", on_ok)
		dialog.bind("<Escape>", on_cancel)

		# Restore saved geometry or default centered, horizontal only (resizable=False vertically)
		cfg = load_config()
		saved_geo = cfg.get("editor_add_story_dialog")
		applied = False
		if saved_geo:
			try:
				# Only restore width+position, not height (since resizable is horizontal only)
				import re as _re
				m = _re.match(r"(\d+)x\d+([+-]\d+[+-]\d+)?", saved_geo)
				if m:
					w = max(int(m.group(1)), 480)
					pos = m.group(2) or ""
					dialog.update_idletasks()
					h = dialog.winfo_reqheight()
					dialog.geometry(f"{w}x{h}{pos}")
					applied = True
			except Exception:
				pass
		if not applied:
			dialog.update_idletasks()
			w, h = 480, dialog.winfo_reqheight()
			rx = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
			ry = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
			dialog.geometry(f"{w}x{h}+{rx}+{ry}")
		dialog.minsize(480, 0)

		self.root.wait_window(dialog)


		title = title_result[0]
		if not title or not title.strip():
			return
		title = title.strip()


		# Auto generate 4-digit Story ID
		slug = self.get_next_story_id()

		# Read catalog
		catalog = []
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					catalog = json.load(f)
			except Exception:
				pass

		existing = next((item for item in catalog if item.get('slug') == slug), None)
		if existing:
			messagebox.showwarning("Chú ý", f"ID/Slug tự động '{slug}' đã tồn tại!")
			return

		# Create story folder
		story_dir = os.path.join(LIBRARY_DIR, slug)
		os.makedirs(story_dir, exist_ok=True)

		# Copy story.html template to library/{slug}/index.html
		story_template = os.path.join(LIBRARY_DIR, "story.html")
		dest_story_html = os.path.join(story_dir, "index.html")
		if os.path.exists(story_template):
			try:
				import shutil
				shutil.copy2(story_template, dest_story_html)
			except Exception as e:
				print(f"Lỗi sao chép template story.html: {e}")

		# Add new story to list
		import datetime
		now = datetime.datetime.now()
		catalog.append({
			"title": title,
			"slug": slug,
			"date": now.strftime("%d/%m/%Y"),
			"timestamp": now.timestamp(),
			"chapters": []
		})

		try:
			with open(CATALOG_PATH, "w", encoding="utf-8") as f:
				json.dump(catalog, f, ensure_ascii=False, indent=4)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể lưu list.json:\n{e}")
			return

		messagebox.showinfo("Thành công", f"Đã thêm truyện mới thành công!\n\nTên: {title}\nID tự động (4 chữ số): {slug}\n\nThư mục: library/{slug}")
		self.load_story_list()
		
		# Auto select in combobox
		new_item = f"{slug} | {title}"
		if new_item in self.story_options:
			self.story_combo.set(new_item)
			self.on_story_selected()

	def save_chapter(self):
		story_value = self.story_combo.get().strip()
		chap_slug = self.chap_entry.get().strip()
		chap_title = self.chap_title_entry.get().strip()
		content = self.content_text.get("1.0", tk.END).strip()

		if not story_value:
			messagebox.showwarning("Chú ý", "Vui lòng chọn Truyện!")
			return
		if not chap_title:
			chap_title = "Oneshot"
		if not content:
			messagebox.showwarning("Chú ý", "Nội dung chương không được để trống!")
			return

		# Parse Story Slug
		if "|" in story_value:
			story_slug, story_title = story_value.split("|", 1)
			story_slug = story_slug.strip()
			story_title = story_title.strip()
		else:
			story_title = story_value
			story_slug = slugify_vn(story_title)

		# Auto assign 6-digit chapter ID if empty
		if not chap_slug:
			chap_slug = self.get_next_chapter_id(story_slug)
			self.chap_entry.delete(0, tk.END)
			self.chap_entry.insert(0, chap_slug)
		else:
			# Ensure safe ID format
			chap_slug = slugify_vn(chap_slug)

		# Directories path
		story_dir = os.path.join(LIBRARY_DIR, story_slug)
		output_dir = os.path.join(story_dir, chap_slug)
		os.makedirs(output_dir, exist_ok=True)

		# Build chapter content blocks (Vietnamese only, base64 CN is empty string)
		paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
		story_data = {
			"title": story_title,
			"chapter_title": chap_title,
			"content": []
		}

		for p in paragraphs:
			p_nfc = unicodedata.normalize('NFC', p)
			story_data["content"].append({
				"cn": base64.b64encode("".encode('utf-8')).decode('utf-8'),
				"vi": base64.b64encode(p_nfc.encode('utf-8')).decode('utf-8')
			})

		# Save data.json
		data_json_path = os.path.join(output_dir, "data.json")
		try:
			with open(data_json_path, "w", encoding="utf-8") as f:
				json.dump(story_data, f, ensure_ascii=False)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể ghi file data.json:\n{e}")
			return

		# Copy reader.html (from root) to library/{story-slug}/{chap-slug}/index.html
		reader_template = os.path.join(BASE_DIR, "reader.html")
		dest_reader_html = os.path.join(output_dir, "index.html")
		if os.path.exists(reader_template):
			try:
				import shutil
				shutil.copy2(reader_template, dest_reader_html)
			except Exception as e:
				print(f"Lỗi sao chép template reader.html: {e}")

		# Copy story.html template to library/{story-slug}/index.html if not present
		story_template = os.path.join(LIBRARY_DIR, "story.html")
		dest_story_html = os.path.join(story_dir, "index.html")
		if os.path.exists(story_template) and not os.path.exists(dest_story_html):
			try:
				import shutil
				shutil.copy2(story_template, dest_story_html)
			except Exception as e:
				print(f"Lỗi sao chép template story.html: {e}")

		# Update list.json catalog
		import datetime
		now = datetime.datetime.now()
		catalog = []
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					catalog = json.load(f)
			except Exception:
				pass

		existing = next((item for item in catalog if item.get('slug') == story_slug), None)
		chap_data = {"id": chap_slug, "name": chap_title, "date": now.strftime("%d/%m/%Y")}

		if not existing:
			catalog.append({
				"title": story_title,
				"slug": story_slug,
				"date": now.strftime("%d/%m/%Y"),
				"timestamp": now.timestamp(),
				"chapters": [chap_data]
			})
		else:
			existing['title'] = story_title
			existing['date'] = now.strftime("%d/%m/%Y")
			existing['timestamp'] = now.timestamp()
			if 'chapters' not in existing:
				existing['chapters'] = []

			# Check if chapter already indexed, otherwise append
			chap_exists = next((c for c in existing['chapters'] if c['id'] == chap_slug), None)
			if chap_exists:
				chap_exists['name'] = chap_title
				chap_exists['date'] = chap_data['date']
			else:
				existing['chapters'].append(chap_data)

		try:
			with open(CATALOG_PATH, "w", encoding="utf-8") as f:
				json.dump(catalog, f, ensure_ascii=False, indent=4)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể cập nhật list.json:\n{e}")
			return

		self.load_story_list()

		# Dọn dẹp editor và điền sẵn ID chương tiếp theo
		next_chap_id = self.get_next_chapter_id(story_slug)
		self.chap_entry.delete(0, tk.END)
		self.chap_entry.insert(0, next_chap_id)
		self.chap_title_entry.delete(0, tk.END)
		self.content_text.delete("1.0", tk.END)

	def pick_json(self):
		file_path = filedialog.askopenfilename(
			title="Chọn data.json",
			filetypes=[("JSON files", "*.json")],
		)
		if not file_path:
			return

		try:
			with open(file_path, "r", encoding="utf-8") as f:
				self.loaded_json = json.load(f)
		except Exception:
			messagebox.showerror("Lỗi", "Không thể đọc file JSON.")
			return

		title = self.loaded_json.get("title", "Không có")
		chap_title = self.loaded_json.get("chapter_title", "")
		content_items = self.loaded_json.get("content", [])
		count = len(content_items)

		# Auto-decode all Vietnamese paragraphs and insert to temp_text
		vi_texts = []
		if isinstance(content_items, list):
			for item in content_items:
				vi = item.get("vi")
				if vi:
					vi_texts.append(safe_decode_b64(vi))

		self.temp_text.delete("1.0", tk.END)
		self.temp_text.insert("1.0", "\n\n".join(vi_texts))

		# Try to auto-detect story slug and chapter slug from directory structure
		norm_path = os.path.normpath(file_path)
		parts = norm_path.split(os.sep)
		detected_story_slug = ""
		detected_chap_slug = ""

		if len(parts) >= 3 and parts[-1].lower() == "data.json":
			detected_chap_slug = parts[-2]
			detected_story_slug = parts[-3]

		# Case A: Loaded from library/{story-id}/{chapter-id}/data.json
		if detected_story_slug and detected_chap_slug and detected_story_slug.lower() != "stories" and detected_story_slug.lower() != "library":
			# Auto select or input story
			found_option = None
			for opt in self.story_options:
				if opt.startswith(f"{detected_story_slug} |"):
					found_option = opt
					break
			
			if found_option:
				self.story_combo.set(found_option)
			else:
				self.story_combo.set(f"{detected_story_slug} | {title}")

			# Auto set chapter ID
			self.chap_entry.delete(0, tk.END)
			self.chap_entry.insert(0, detected_chap_slug)

			# Auto set chapter Title
			if chap_title:
				self.chap_title_entry.delete(0, tk.END)
				self.chap_title_entry.insert(0, chap_title)

		# Case B: Loaded from stories/{story-slug}/data.json (generated by builder.py)
		elif detected_story_slug and detected_story_slug.lower() == "stories":
			# Search the story options for a story that has the same title
			found_option = None
			for opt in self.story_options:
				if "|" in opt:
					slug_opt, title_opt = opt.split("|", 1)
					if title_opt.strip().lower() == title.strip().lower():
						found_option = opt
						break
			
			if found_option:
				self.story_combo.set(found_option)
				story_id = found_option.split("|")[0].strip()
				
				# Get next chapter ID automatically!
				next_chap_id = self.get_next_chapter_id(story_id)
				self.chap_entry.delete(0, tk.END)
				self.chap_entry.insert(0, next_chap_id)
			
			# Auto set chapter Title if it exists
			if chap_title:
				self.chap_title_entry.delete(0, tk.END)
				self.chap_title_entry.insert(0, chap_title)

		# Update status label
		info_str = f"Đã nạp: {os.path.basename(file_path)} | Truyện: {title} | Chương: {chap_title if chap_title else 'Chưa rõ'} | {count} đoạn"
		self.temp_status.config(text=info_str, fg="#10b981")

	def process_json(self):
		new_text = self.temp_text.get("1.0", tk.END).strip()
		if not new_text:
			messagebox.showwarning("Chú ý", "Cửa sổ temp đang trống hoặc chưa có nội dung.")
			return

		if not self.loaded_json:
			self.loaded_json = {}

		# Set chapter title from JSON if available and editor is empty
		loaded_chap_title = self.loaded_json.get("chapter_title", "")
		if loaded_chap_title and not self.chap_title_entry.get().strip():
			self.chap_title_entry.delete(0, tk.END)
			self.chap_title_entry.insert(0, loaded_chap_title)

		# Fallback to general title if chapter_title is not present
		if not self.chap_entry.get().strip() and self.loaded_json.get("title"):
			self.chap_entry.insert(0, slugify_vn(self.loaded_json.get("title")))

		existing = self.content_text.get("1.0", tk.END).strip()

		if existing:
			should_append = messagebox.askyesno(
				"Xác nhận",
				"Editor đang có sẵn dữ liệu. Bạn muốn viết tiếp xuống dưới?",
			)
			if should_append:
				self.content_text.insert(tk.END, "\n\n" + new_text)
			else:
				self.content_text.delete("1.0", tk.END)
				self.content_text.insert("1.0", new_text)
		else:
			self.content_text.delete("1.0", tk.END)
			self.content_text.insert("1.0", new_text)

	def move_selected_text(self):
		try:
			selected_text = self.temp_text.get("sel.first", "sel.last")
			if not selected_text.strip():
				return
			
			# Auto-fill chapter title if first line contains "Chương" and title field is empty
			if not self.chap_title_entry.get().strip():
				first_line = selected_text.strip().split("\n")[0].strip()
				if re.search(r"chương", first_line, re.IGNORECASE):
					self.chap_title_entry.delete(0, tk.END)
					self.chap_title_entry.insert(0, first_line)
			
			# Cut the text from temp_text
			self.temp_text.delete("sel.first", "sel.last")
			
			# Paste to content_text
			existing = self.content_text.get("1.0", tk.END).strip()
			if existing:
				self.content_text.insert(tk.END, "\n\n" + selected_text)
			else:
				self.content_text.insert("1.0", selected_text)
				
		except tk.TclError:
			messagebox.showwarning("Chú ý", "Vui lòng bôi đen (chọn) phần văn bản cần chuyển trong cửa sổ bên phải.")



	# --- HỆ THỐNG PHÂN CHƯƠNG TỰ ĐỘNG ---

	DEFAULT_SPLIT_PATTERNS = [
		("Chương X (mặc định)", r"^chương\s+[\d]+"),
		("Chương X: Tiêu đề", r"^chương\s+[\d]+[\s:：·]"),
		("Thứ X chương", r"^thứ\s+\d+\s+chương"),
		("Tiết X:", r"^tiết\s+[\d\w]+[\s:：]"),
		("Chapter X (English)", r"^chapter\s+\d+"),
	]

	def get_split_patterns(self):
		"""Return list of (name, regex) for the pattern selector, merging defaults + saved custom."""
		cfg = load_config()
		saved = cfg.get("split_patterns", [])
		# saved is list of [name, regex] from config
		result = list(self.DEFAULT_SPLIT_PATTERNS)
		for item in saved:
			if isinstance(item, (list, tuple)) and len(item) == 2:
				name, rx = item
				# Skip if already in defaults (by regex)
				if not any(rx == r for _, r in result):
					result.append((name, rx))
		return result

	def save_split_pattern(self, name, regex):
		"""Persist a new custom pattern to config."""
		cfg = load_config()
		saved = cfg.get("split_patterns", [])
		# Avoid duplicate regex
		saved = [p for p in saved if p[1] != regex]
		saved.append([name, regex])
		save_config({"split_patterns": saved})

	def detect_chapters(self, text, pattern_regex):
		"""
		Split paragraphs (separated by \\n\\n) into chapters based on a regex header pattern.
		Returns list of {"title": str, "paragraphs": [str]} dicts.
		Paragraphs before the first header are grouped under title="".
		"""
		try:
			compiled = re.compile(pattern_regex, re.IGNORECASE | re.MULTILINE)
		except re.error:
			return []

		paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
		chapters = []
		current_title = None
		current_paras = []

		for para in paragraphs:
			if compiled.match(para):
				# Flush previous group
				if current_title is not None or current_paras:
					chapters.append({"title": current_title or "", "paragraphs": current_paras})
				current_title = para.strip()
				current_paras = []
			else:
				current_paras.append(para)

		# Flush last group
		if current_title is not None or current_paras:
			chapters.append({"title": current_title or "", "paragraphs": current_paras})

		return chapters

	def open_split_chapters_dialog(self):
		"""Open the auto-split chapters dialog."""
		raw_text = self.temp_text.get("1.0", tk.END).strip()
		if not raw_text:
			messagebox.showwarning("Chú ý", "Cửa sổ bên phải đang trống. Hãy load file JSON trước!")
			return

		patterns = self.get_split_patterns()

		# --- Build Dialog ---
		dlg = tk.Toplevel(self.root)
		dlg.title("🔪 Phân Chương Tự Động")
		dlg.configure(bg="#09090b")
		dlg.transient(self.root)
		dlg.grab_set()
		dlg.resizable(True, True)

		# Restore saved geometry
		cfg = load_config()
		geo = cfg.get("editor_split_dialog", "860x640")
		dlg.geometry(geo)
		dlg.minsize(700, 500)

		def on_dlg_close():
			save_config({"editor_split_dialog": dlg.geometry()})
			dlg.destroy()
		dlg.protocol("WM_DELETE_WINDOW", on_dlg_close)

		# ── HEADER ──
		hdr = tk.Frame(dlg, bg="#18181b", pady=10)
		hdr.pack(fill=tk.X)
		tk.Label(hdr, text="🔪 Phân Chương Tự Động", fg="#ffffff", bg="#18181b",
				 font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=16)

		# ── STEP 1: Pattern selector ──
		step1 = tk.Frame(dlg, bg="#18181b", padx=16, pady=8)
		step1.pack(fill=tk.X, padx=12, pady=(8, 0))
		tk.Label(step1, text="BƯỚC 1 — Chọn pattern nhận diện header chương:", fg="#a1a1aa",
				 bg="#18181b", font=("Arial", 9, "bold")).pack(anchor="w")

		pattern_row = tk.Frame(step1, bg="#18181b")
		pattern_row.pack(fill=tk.X, pady=(6, 0))

		pattern_names = [p[0] for p in patterns]
		pattern_var = tk.StringVar(value=pattern_names[0])
		pattern_combo = ttk.Combobox(pattern_row, textvariable=pattern_var, values=pattern_names,
									 state="readonly", font=("Arial", 9), width=28)
		pattern_combo.pack(side=tk.LEFT, padx=(0, 8))

		regex_var = tk.StringVar(value=patterns[0][1])
		regex_entry = tk.Entry(pattern_row, textvariable=regex_var, bg="#27272a", fg="#e4e4e7",
							   insertbackground="white", font=("Consolas", 9),
							   highlightthickness=1, highlightbackground="#3f3f46",
							   highlightcolor="#8b5cf6", relief="flat")
		regex_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 8))

		def on_pattern_select(event=None):
			sel = pattern_combo.get()
			for name, rx in patterns:
				if name == sel:
					regex_var.set(rx)
					break

		pattern_combo.bind("<<ComboboxSelected>>", on_pattern_select)

		# Save custom pattern button
		def save_custom_pattern():
			name = pattern_var.get().strip()
			rx = regex_var.get().strip()
			if not rx:
				return
			if not any(name == n for n, _ in patterns):
				name = f"Tuỳ chỉnh: {rx[:20]}"
			self.save_split_pattern(name, rx)
			messagebox.showinfo("Đã lưu", f"Pattern '{name}' đã được lưu vào config.", parent=dlg)

		tk.Button(pattern_row, text="💾 Lưu pattern", bg="#3f3f46", fg="#ffffff",
				  relief="flat", borderwidth=0, padx=8, pady=4, font=("Arial", 8),
				  cursor="hand2", command=save_custom_pattern).pack(side=tk.LEFT, padx=(0, 4))

		# ── Detected chapters state ──
		detected_chapters = []  # list of {"title": str, "paragraphs": [str], "title_var": StringVar}
		chapter_rows_frame = None

		# ── STEP 2: Preview ──
		step2_header = tk.Frame(dlg, bg="#09090b", padx=16, pady=6)
		step2_header.pack(fill=tk.X, padx=12, pady=(10, 0))
		count_label = tk.Label(step2_header, text="BƯỚC 2 — Xem & chỉnh sửa tên chương:", fg="#a1a1aa",
							   bg="#09090b", font=("Arial", 9, "bold"))
		count_label.pack(side=tk.LEFT)

		tk.Button(step2_header, text="🔍 Phân tích lại", bg="#8b5cf6", fg="#ffffff",
				  relief="flat", borderwidth=0, padx=10, pady=3, font=("Arial", 9, "bold"),
				  cursor="hand2", command=lambda: run_detect()).pack(side=tk.RIGHT)

		# Scrollable list
		list_outer = tk.Frame(dlg, bg="#09090b")
		list_outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 0))

		canvas = tk.Canvas(list_outer, bg="#09090b", highlightthickness=0)
		scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
		canvas.configure(yscrollcommand=scrollbar.set)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
		canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

		inner_frame = tk.Frame(canvas, bg="#09090b")
		canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")

		def on_inner_configure(event):
			canvas.configure(scrollregion=canvas.bbox("all"))
		def on_canvas_configure(event):
			canvas.itemconfig(canvas_window, width=event.width)
		inner_frame.bind("<Configure>", on_inner_configure)
		canvas.bind("<Configure>", on_canvas_configure)

		# Mouse wheel scroll
		def on_mousewheel(event):
			canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
		canvas.bind_all("<MouseWheel>", on_mousewheel)

		def build_chapter_list():
			for w in inner_frame.winfo_children():
				w.destroy()

			if not detected_chapters:
				tk.Label(inner_frame, text="Không phát hiện được chương nào với pattern này.",
						 fg="#ef4444", bg="#09090b", font=("Arial", 10)).pack(pady=20)
				return

			# Column headers
			hrow = tk.Frame(inner_frame, bg="#27272a")
			hrow.pack(fill=tk.X, padx=4, pady=(4, 2))
			tk.Label(hrow, text="#", fg="#71717a", bg="#27272a", font=("Arial", 8, "bold"), width=4).pack(side=tk.LEFT, padx=(8,0))
			tk.Label(hrow, text="ID", fg="#71717a", bg="#27272a", font=("Arial", 8, "bold"), width=8).pack(side=tk.LEFT, padx=4)
			tk.Label(hrow, text="Tên chương (có thể sửa)", fg="#71717a", bg="#27272a", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
			tk.Label(hrow, text="Đoạn", fg="#71717a", bg="#27272a", font=("Arial", 8, "bold"), width=6).pack(side=tk.RIGHT, padx=8)

			for i, chap in enumerate(detected_chapters):
				row_bg = "#18181b" if i % 2 == 0 else "#1c1c1f"
				row = tk.Frame(inner_frame, bg=row_bg)
				row.pack(fill=tk.X, padx=4, pady=1)

				tk.Label(row, text=str(i+1), fg="#52525b", bg=row_bg, font=("Arial", 8), width=4).pack(side=tk.LEFT, padx=(8,0), pady=4)
				tk.Label(row, text=chap["id"], fg="#3b82f6", bg=row_bg, font=("Consolas", 9), width=8).pack(side=tk.LEFT, padx=4)

				entry = tk.Entry(row, textvariable=chap["title_var"], bg=row_bg, fg="#e4e4e7",
								 insertbackground="white", font=("Arial", 9), relief="flat",
								 highlightthickness=1, highlightbackground="#27272a",
								 highlightcolor="#8b5cf6")
				entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=4)

				tk.Label(row, text=str(len(chap["paragraphs"])), fg="#10b981", bg=row_bg,
						 font=("Arial", 8), width=6).pack(side=tk.RIGHT, padx=8)

		def run_detect():
			nonlocal detected_chapters
			rx = regex_var.get().strip()
			if not rx:
				messagebox.showwarning("Chú ý", "Vui lòng nhập regex pattern!", parent=dlg)
				return

			# Validate regex
			try:
				re.compile(rx, re.IGNORECASE)
			except re.error as e:
				messagebox.showerror("Regex lỗi", str(e), parent=dlg)
				return

			raw = self.temp_text.get("1.0", tk.END).strip()
			chapters_raw = self.detect_chapters(raw, rx)

			# Get next chapter ID from story
			story_value = story_combo.get().strip()
			story_slug = ""
			if "|" in story_value:
				story_slug = story_value.split("|", 1)[0].strip()

			start_id = self.get_next_chapter_id(story_slug) if story_slug else "000001"
			try:
				id_int = int(start_id)
			except ValueError:
				id_int = 1

			detected_chapters = []
			for i, ch in enumerate(chapters_raw):
				chap_id = f"{id_int + i:06d}"
				title_val = ch["title"] if ch["title"] else f"Chương {id_int + i}"
				detected_chapters.append({
					"id": chap_id,
					"title_var": tk.StringVar(value=title_val),
					"paragraphs": ch["paragraphs"],
				})

			n = len(detected_chapters)
			count_label.config(
				text=f"BƯỚC 2 — Xem & chỉnh sửa ({n} chương phát hiện):",
				fg="#10b981" if n > 0 else "#ef4444"
			)
			save_btn.config(text=f"💾 Lưu tất cả ({n} chương)")
			build_chapter_list()

		# ── STEP 3: Story selector + Save ──
		tk.Frame(dlg, bg="#27272a", height=1).pack(fill=tk.X, padx=12, pady=(8, 0))
		step3 = tk.Frame(dlg, bg="#18181b", padx=16, pady=10)
		step3.pack(fill=tk.X, padx=12, pady=(0, 0))
		tk.Label(step3, text="BƯỚC 3 — Chọn truyện để lưu:", fg="#a1a1aa", bg="#18181b",
				 font=("Arial", 9, "bold")).pack(anchor="w", pady=(0, 6))

		story_row = tk.Frame(step3, bg="#18181b")
		story_row.pack(fill=tk.X)

		story_combo = ttk.Combobox(story_row, values=self.story_options, font=("Arial", 10),
								   state="readonly")
		# Pre-select current story if available
		cur = self.story_combo.get().strip()
		if cur in self.story_options:
			story_combo.set(cur)
		story_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
		story_combo.bind("<<ComboboxSelected>>", lambda e: run_detect() if detected_chapters else None)

		tk.Frame(dlg, bg="#27272a", height=1).pack(fill=tk.X, padx=12)
		btn_row = tk.Frame(dlg, bg="#09090b", pady=10)
		btn_row.pack(fill=tk.X, padx=12)

		tk.Button(btn_row, text="Hủy", bg="#27272a", fg="#a1a1aa", activebackground="#3f3f46",
				  relief="flat", borderwidth=0, padx=16, pady=6, font=("Arial", 9),
				  cursor="hand2", command=on_dlg_close).pack(side=tk.RIGHT, padx=(6, 0))

		save_btn = tk.Button(btn_row, text="💾 Lưu tất cả (0 chương)", bg="#8b5cf6", fg="#ffffff",
				  activebackground="#7c3aed", relief="flat", borderwidth=0,
				  padx=16, pady=6, font=("Arial", 9, "bold"), cursor="hand2",
				  command=lambda: self.save_all_split_chapters(dlg, story_combo, detected_chapters, on_dlg_close))
		save_btn.pack(side=tk.RIGHT)

		# Initial detect
		run_detect()

	def save_all_split_chapters(self, dlg, story_combo, detected_chapters, close_callback):
		"""Save all detected chapters to the library."""
		import datetime
		import shutil

		story_value = story_combo.get().strip()
		if not story_value:
			messagebox.showwarning("Chú ý", "Vui lòng chọn Truyện!", parent=dlg)
			return
		if not detected_chapters:
			messagebox.showwarning("Chú ý", "Không có chương nào để lưu!", parent=dlg)
			return

		# Parse story slug + title
		if "|" in story_value:
			story_slug, story_title = story_value.split("|", 1)
			story_slug = story_slug.strip()
			story_title = story_title.strip()
		else:
			story_title = story_value
			story_slug = slugify_vn(story_title)

		# Check chapters without content
		empty = [ch for ch in detected_chapters if not ch["paragraphs"]]
		if empty:
			names = ", ".join(ch["title_var"].get()[:30] for ch in empty[:3])
			if not messagebox.askyesno("Chú ý",
				f"{len(empty)} chương không có nội dung ({names}...).\nBạn vẫn muốn lưu các chương có nội dung?",
				parent=dlg):
				return

		now = datetime.datetime.now()
		story_dir = os.path.join(LIBRARY_DIR, story_slug)
		os.makedirs(story_dir, exist_ok=True)

		# Copy story.html template if not present
		story_template = os.path.join(LIBRARY_DIR, "story.html")
		dest_story_html = os.path.join(story_dir, "index.html")
		if os.path.exists(story_template) and not os.path.exists(dest_story_html):
			try:
				shutil.copy2(story_template, dest_story_html)
			except Exception:
				pass

		# Load catalog
		catalog = []
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					catalog = json.load(f)
			except Exception:
				pass

		existing_story = next((item for item in catalog if item.get("slug") == story_slug), None)
		if not existing_story:
			existing_story = {
				"title": story_title, "slug": story_slug,
				"date": now.strftime("%d/%m/%Y"), "timestamp": now.timestamp(),
				"chapters": []
			}
			catalog.append(existing_story)

		saved_count = 0
		errors = []

		for ch in detected_chapters:
			if not ch["paragraphs"]:
				continue

			chap_slug = ch["id"]
			chap_title = ch["title_var"].get().strip() or f"Chương {chap_slug}"
			output_dir = os.path.join(story_dir, chap_slug)
			os.makedirs(output_dir, exist_ok=True)

			# Build data.json content blocks
			story_data = {
				"title": story_title,
				"chapter_title": chap_title,
				"content": []
			}
			for para in ch["paragraphs"]:
				p_nfc = unicodedata.normalize("NFC", para)
				story_data["content"].append({
					"cn": base64.b64encode("".encode("utf-8")).decode("utf-8"),
					"vi": base64.b64encode(p_nfc.encode("utf-8")).decode("utf-8"),
				})

			# Write data.json
			data_json_path = os.path.join(output_dir, "data.json")
			try:
				with open(data_json_path, "w", encoding="utf-8") as f:
					json.dump(story_data, f, ensure_ascii=False)
			except Exception as e:
				errors.append(f"{chap_slug}: {e}")
				continue

			# Copy reader.html template
			reader_template = os.path.join(BASE_DIR, "reader.html")
			dest_reader_html = os.path.join(output_dir, "index.html")
			if os.path.exists(reader_template):
				try:
					shutil.copy2(reader_template, dest_reader_html)
				except Exception:
					pass

			# Update catalog
			chap_data = {"id": chap_slug, "name": chap_title, "date": now.strftime("%d/%m/%Y")}
			chap_exists = next((c for c in existing_story["chapters"] if c["id"] == chap_slug), None)
			if chap_exists:
				chap_exists["name"] = chap_title
				chap_exists["date"] = chap_data["date"]
			else:
				existing_story["chapters"].append(chap_data)

			saved_count += 1

		# Update story timestamp
		existing_story["date"] = now.strftime("%d/%m/%Y")
		existing_story["timestamp"] = now.timestamp()

		# Save catalog
		try:
			with open(CATALOG_PATH, "w", encoding="utf-8") as f:
				json.dump(catalog, f, ensure_ascii=False, indent=4)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể cập nhật list.json:\n{e}", parent=dlg)
			return

		self.load_story_list()

		if errors:
			messagebox.showwarning("Hoàn thành (có lỗi)",
				f"Đã lưu {saved_count}/{len(detected_chapters)} chương.\n\nLỗi:\n" + "\n".join(errors[:5]),
				parent=dlg)
		else:
			messagebox.showinfo("Thành công",
				f"✅ Đã lưu {saved_count} chương vào truyện '{story_title}'!", parent=dlg)

		close_callback()

	# --- HỆ THỐNG TÌM KIẾM CHO CỬA SỔ TEMP ---

	def get_match_coords(self):
		ranges = self.temp_text.tag_ranges("match")
		return [(str(ranges[i]), str(ranges[i+1])) for i in range(0, len(ranges), 2)]

	def schedule_search(self, event=None):
		if hasattr(self, '_search_timer') and self._search_timer:
			self.root.after_cancel(self._search_timer)
		self._search_timer = self.root.after(500, self.perform_search)

	def perform_search(self, event=None):
		self.temp_text.tag_remove("match", "1.0", tk.END)
		self.temp_text.tag_remove("active_match", "1.0", tk.END)
		self.current_match_idx = -1

		query = self.search_entry.get()
		if not query:
			self.search_status.config(text="0/0", fg="#a1a1aa")
			return

		is_regex = self.regex_var.get()
		
		try:
			if not is_regex:
				query = re.escape(query)
			
			pattern = re.compile(query, re.IGNORECASE)
			text_content = self.temp_text.get("1.0", tk.END)
			
			# Collect all match ranges first, then apply in one batch
			MAX_MATCHES = 2000
			flat_ranges = []
			for match in pattern.finditer(text_content):
				if match.start() == match.end():
					continue  # Bỏ qua các match rỗng
				flat_ranges.append(f"1.0+{match.start()}c")
				flat_ranges.append(f"1.0+{match.end()}c")
				if len(flat_ranges) >= MAX_MATCHES * 2:
					break

			if flat_ranges:
				self.temp_text.tag_add("match", *flat_ranges)
				
		except Exception:
			self.search_status.config(text="Regex lỗi", fg="#ef4444")
			return

		coords = self.get_match_coords()
		if coords:
			self.current_match_idx = 0
			self.highlight_active_match()
		else:
			self.search_status.config(text="0/0", fg="#ef4444")


	def highlight_active_match(self):
		self.temp_text.tag_remove("active_match", "1.0", tk.END)
		coords = self.get_match_coords()
		
		if not coords:
			self.current_match_idx = -1
			self.search_status.config(text="0/0", fg="#ef4444")
			return

		if self.current_match_idx >= len(coords):
			self.current_match_idx = len(coords) - 1
		elif self.current_match_idx < 0:
			self.current_match_idx = 0

		start, end = coords[self.current_match_idx]
		self.temp_text.tag_add("active_match", start, end)
		self.temp_text.see(start)
		
		total = len(coords)
		self.search_status.config(text=f"{self.current_match_idx + 1}/{total}", fg="#10b981")

	def find_next(self, event=None):
		coords = self.get_match_coords()
		if not coords:
			return "break"
			
		active_ranges = self.temp_text.tag_ranges("active_match")
		if active_ranges:
			current_pos = str(active_ranges[0])
			op = ">"
		else:
			current_pos = self.temp_text.index(tk.INSERT)
			op = ">="
			
		next_idx = 0
		for i, (start, end) in enumerate(coords):
			if self.temp_text.compare(start, op, current_pos):
				next_idx = i
				break
				
		self.current_match_idx = next_idx
		self.highlight_active_match()
		return "break"

	def find_prev(self, event=None):
		coords = self.get_match_coords()
		if not coords:
			return "break"
			
		active_ranges = self.temp_text.tag_ranges("active_match")
		if active_ranges:
			current_pos = str(active_ranges[0])
		else:
			current_pos = self.temp_text.index(tk.INSERT)
			
		prev_idx = len(coords) - 1
		for i in range(len(coords)-1, -1, -1):
			start, end = coords[i]
			if self.temp_text.compare(start, "<", current_pos):
				prev_idx = i
				break
				
		self.current_match_idx = prev_idx
		self.highlight_active_match()
		return "break"

	def select_above_match(self, event=None):
		coords = self.get_match_coords()
		if not coords or self.current_match_idx < 0 or self.current_match_idx >= len(coords):
			return "break"
		
		start, end = coords[self.current_match_idx]
		
		self.temp_text.tag_remove("sel", "1.0", tk.END)
		self.temp_text.tag_add("sel", "1.0", start)
		
		self.temp_text.mark_set("insert", "1.0")
		self.temp_text.see("1.0")
		self.temp_text.focus_set()
		return "break"

	def show_search_dialog(self, event=None):
		if not self.search_frame.winfo_ismapped():
			self.temp_text.pack_forget()
			self.search_frame.pack(fill="x", padx=16, pady=(0, 6))
			self.temp_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
		
		self.search_entry.focus_set()
		self.search_entry.selection_range(0, tk.END)
		self.perform_search()
		return "break"

	def hide_search_dialog(self, event=None):
		if self.search_frame.winfo_ismapped():
			self.search_frame.pack_forget()
			self.temp_text.focus_set()
		self.temp_text.tag_remove("match", "1.0", tk.END)
		self.temp_text.tag_remove("active_match", "1.0", tk.END)
		self.current_match_idx = -1
		return "break"


if __name__ == "__main__":
	root = tk.Tk()
	style = ttk.Style()
	style.theme_use("clam")
	root.option_add("*TCombobox*Listbox.background", "#09090b")
	root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
	app = ChapterEditorApp(root)
	root.mainloop()
