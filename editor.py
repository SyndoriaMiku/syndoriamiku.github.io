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
		self.root.geometry("1300x750")
		self.root.configure(bg="#09090b")

		self.loaded_json = None
		self.story_options = []

		self.setup_ui()
		self.load_story_list()

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

	def add_new_story(self):
		default_title = ""
		if self.loaded_json and "title" in self.loaded_json:
			default_title = self.loaded_json.get("title", "")

		title = simpledialog.askstring(
			"Thêm Truyện Mới",
			"Nhập Tên hiển thị của truyện mới:",
			initialvalue=default_title,
			parent=self.root
		)
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



	# --- HỆ THỐNG TÌM KIẾM CHO CỬA SỔ TEMP ---
	def get_match_coords(self):
		ranges = self.temp_text.tag_ranges("match")
		return [(str(ranges[i]), str(ranges[i+1])) for i in range(0, len(ranges), 2)]

	def schedule_search(self, event=None):
		if hasattr(self, '_search_timer') and self._search_timer:
			self.root.after_cancel(self._search_timer)
		self._search_timer = self.root.after(300, self.perform_search)

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
			
			for match in pattern.finditer(text_content):
				if match.start() == match.end():
					continue # Bỏ qua các match rỗng
				start_idx = f"1.0+{match.start()}c"
				end_idx = f"1.0+{match.end()}c"
				self.temp_text.tag_add("match", start_idx, end_idx)
				
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
		self.current_match_idx = (self.current_match_idx + 1) % len(coords)
		self.highlight_active_match()
		return "break"

	def find_prev(self, event=None):
		coords = self.get_match_coords()
		if not coords:
			return "break"
		self.current_match_idx = (self.current_match_idx - 1) % len(coords)
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
