import base64
import json
import os
import re
import shutil
import tempfile
import unicodedata
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from editor_widgets import StorySearchCombo, StyledScrolledText, story_options, configure_theme

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CATALOG_PATH = os.path.join(LIBRARY_DIR, "list.json")
CONFIG_PATH = os.path.join(BASE_DIR, "editor_config.json")


def delete_library_chapter(story_slug, chapter_id):
	"""Remove chapter files and atomically update the catalog; rollback on failure."""
	for value in (story_slug, chapter_id):
		if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
			raise ValueError("Mã truyện hoặc chương không hợp lệ.")
	library_root = os.path.realpath(LIBRARY_DIR)
	story_dir = os.path.join(library_root, story_slug)
	chapter_dir = os.path.join(story_dir, chapter_id)
	for path in (story_dir, chapter_dir):
		if os.path.normcase(os.path.realpath(path)) != os.path.normcase(path):
			raise ValueError("Không xóa chương qua đường dẫn liên kết.")
	with open(CATALOG_PATH, "r", encoding="utf-8") as f:
		catalog = json.load(f)
	story = next((item for item in catalog if item.get("slug") == story_slug), None)
	if story is None or not any(ch.get("id") == chapter_id for ch in story.get("chapters", [])):
		raise ValueError("Chương không còn trong danh mục. Hãy chọn lại chương.")
	if os.path.lexists(chapter_dir) and not os.path.isdir(chapter_dir):
		raise ValueError("Đường dẫn chương không phải thư mục.")

	staging = None
	catalog_tmp = None
	try:
		if os.path.isdir(chapter_dir):
			staging = tempfile.mkdtemp(prefix=".delete-chapter-", dir=story_dir)
			os.replace(chapter_dir, os.path.join(staging, "chapter"))
		story["chapters"] = [ch for ch in story["chapters"] if ch.get("id") != chapter_id]
		fd, catalog_tmp = tempfile.mkstemp(prefix=".list-", suffix=".json", dir=library_root)
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			json.dump(catalog, f, ensure_ascii=False, indent=4)
		os.replace(catalog_tmp, CATALOG_PATH)
		catalog_tmp = None
	except Exception:
		if staging:
			staged_chapter = os.path.join(staging, "chapter")
			if os.path.exists(staged_chapter):
				os.replace(staged_chapter, chapter_dir)
			os.rmdir(staging)
		raise
	finally:
		if catalog_tmp and os.path.exists(catalog_tmp):
			os.remove(catalog_tmp)

	cleanup_warning = None
	if staging:
		try:
			shutil.rmtree(staging)
		except OSError as error:
			cleanup_warning = f"Chương đã được gỡ khỏi thư viện, nhưng chưa dọn được dữ liệu tạm:\n{staging}\n{error}"
	return catalog, cleanup_warning


def delete_library_story(story_slug):
	"""Remove one story directory and atomically update the catalog."""
	if not re.fullmatch(r"[A-Za-z0-9_-]+", story_slug):
		raise ValueError("Mã truyện không hợp lệ.")
	library_root = os.path.realpath(LIBRARY_DIR)
	story_dir = os.path.join(library_root, story_slug)
	if os.path.normcase(os.path.realpath(story_dir)) != os.path.normcase(story_dir):
		raise ValueError("Không xóa truyện qua đường dẫn liên kết.")
	with open(CATALOG_PATH, "r", encoding="utf-8") as f:
		catalog = json.load(f)
	if not any(item.get("slug") == story_slug for item in catalog):
		raise ValueError("Truyện không còn trong danh mục. Hãy chọn lại truyện.")
	if os.path.lexists(story_dir) and not os.path.isdir(story_dir):
		raise ValueError("Đường dẫn truyện không phải thư mục.")

	staging = None
	catalog_tmp = None
	try:
		if os.path.isdir(story_dir):
			staging = tempfile.mkdtemp(prefix=".delete-story-", dir=library_root)
			os.replace(story_dir, os.path.join(staging, "story"))
		catalog = [item for item in catalog if item.get("slug") != story_slug]
		fd, catalog_tmp = tempfile.mkstemp(prefix=".list-", suffix=".json", dir=library_root)
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			json.dump(catalog, f, ensure_ascii=False, indent=4)
		os.replace(catalog_tmp, CATALOG_PATH)
		catalog_tmp = None
	except Exception:
		if staging:
			staged_story = os.path.join(staging, "story")
			if os.path.exists(staged_story):
				os.replace(staged_story, story_dir)
			os.rmdir(staging)
		raise
	finally:
		if catalog_tmp and os.path.exists(catalog_tmp):
			os.remove(catalog_tmp)

	cleanup_warning = None
	if staging:
		try:
			shutil.rmtree(staging)
		except OSError as error:
			cleanup_warning = f"Truyện đã được gỡ khỏi thư viện, nhưng chưa dọn được dữ liệu tạm:\n{staging}\n{error}"
	return catalog, cleanup_warning


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
	# Keep native Text editing semantics (selection replacement, cursor and undo).
	widget.configure(exportselection=False, undo=True, autoseparators=True)
	def select_all(event=None):
		widget.tag_add("sel", "1.0", "end-1c")
		return "break"

	def action(virtual):
		def invoke(event=None):
			widget.event_generate(virtual)
			return "break"
		return invoke

	widget.bind("<<SelectAll>>", select_all)
	for key in ("a", "A"):
		widget.bind(f"<Control-{key}>", select_all)
	for keys, virtual in (("cC", "<<Copy>>"), ("xX", "<<Cut>>"),
		("vV", "<<Paste>>"), ("zZ", "<<Undo>>"), ("yY", "<<Redo>>")):
		for key in keys:
			widget.bind(f"<Control-{key}>", action(virtual))
	widget.bind("<Control-Shift-Z>", action("<<Redo>>"))
	widget.bind("<Control-Shift-z>", action("<<Redo>>"))

	menu = tk.Menu(widget, tearoff=0, bg="#172338", fg="#e2e8f0",
		activebackground="#0f766e", activeforeground="white", bd=0)
	for label, virtual, shortcut in (("Hoàn tác", "<<Undo>>", "Ctrl+Z"),
		("Làm lại", "<<Redo>>", "Ctrl+Y"), ("Cắt", "<<Cut>>", "Ctrl+X"),
		("Sao chép", "<<Copy>>", "Ctrl+C"), ("Dán", "<<Paste>>", "Ctrl+V"),
		("Chọn tất cả", "<<SelectAll>>", "Ctrl+A")):
		menu.add_command(label=label, accelerator=shortcut, command=action(virtual))

	def popup(event):
		widget.focus_set()
		try:
			menu.tk_popup(event.x_root, event.y_root)
		finally:
			menu.grab_release()
		return "break"
	widget.bind("<Button-3>", popup)


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
		self.root.configure(bg="#0b1220")

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


	def _button(self, parent, text, command, primary=False):
		return tk.Button(parent, text=text, command=command, bg="#0f766e" if primary else "#25344b",
			fg="#ffffff", activebackground="#115e59" if primary else "#334155",
			activeforeground="white", font=("Segoe UI", 10, "bold"), bd=0,
			relief="flat", padx=14, pady=8, cursor="hand2")

	def setup_ui(self):
		configure_theme(self.root)
		self.root.minsize(1040, 680)
		header = tk.Frame(self.root, bg="#0b1220")
		header.pack(fill="x", padx=24, pady=(20, 14))
		tk.Label(header, text="THƯ VIỆN  /  BIÊN TẬP", fg="#5eead4", bg="#0b1220",
			font=("Segoe UI", 9, "bold")).pack(anchor="w")
		tk.Label(header, text="Không gian biên tập", fg="#f8fafc", bg="#0b1220",
			font=("Segoe UI", 23, "bold")).pack(anchor="w", pady=(3, 2))
		tk.Label(header, text="Chọn truyện · Chỉnh sửa nội dung · Phân chương và lưu vào thư viện",
			fg="#94a3b8", bg="#0b1220", font=("Segoe UI", 10)).pack(anchor="w")
		panes = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#0b1220", bd=0,
			sashwidth=12, sashrelief="flat", showhandle=False)
		panes.pack(fill="both", expand=True, padx=24, pady=(0, 16))
		left = tk.Frame(panes, bg="#111c2e", highlightthickness=1, highlightbackground="#263449")
		right = tk.Frame(panes, bg="#111c2e", highlightthickness=1, highlightbackground="#263449")
		panes.add(left, minsize=460, stretch="always")
		panes.add(right, minsize=460, stretch="always")
		self.build_left(left)
		self.build_right(right)
		footer = tk.Frame(self.root, bg="#0b1220")
		footer.pack(fill="x", padx=24, pady=(0, 12))
		self.library_status = tk.Label(footer, text="Thư viện", bg="#0b1220", fg="#94a3b8", font=("Segoe UI", 9))
		self.library_status.pack(side="left")
		tk.Label(footer, text="Ctrl + F  Tìm trong nguồn    •    Kéo vạch giữa để đổi độ rộng", bg="#0b1220",
			fg="#64748b", font=("Segoe UI", 9)).pack(side="right")

	def build_left(self, parent):
		tk.Label(parent, text="01   Biên tập chương", fg="#f8fafc", bg="#111c2e",
			font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 12))
		form = tk.Frame(parent, bg="#111c2e")
		form.pack(fill="both", expand=True, padx=18)
		tk.Label(form, text="TRUYỆN  ·  Gõ tên hoặc mã để tìm", fg="#94a3b8", bg="#111c2e",
			font=("Segoe UI", 9, "bold")).pack(anchor="w")
		story_row = tk.Frame(form, bg="#111c2e")
		story_row.pack(fill="x", pady=(6, 12))
		delete_story_button = self._button(story_row, "Xóa truyện", self.delete_story)
		delete_story_button.config(bg="#9f1239", activebackground="#be123c")
		delete_story_button.pack(side="right", padx=(8, 0))
		self._button(story_row, "+ Truyện mới", self.add_new_story).pack(side="right", padx=(8, 0))
		self.story_combo = StorySearchCombo(story_row, values=self.story_options, font=("Segoe UI", 10), width=20)
		self.story_combo.pack(side="left", fill="x", expand=True)
		self.story_combo.bind("<<ComboboxSelected>>", self.on_story_selected, add="+")
		tk.Label(form, text="CHƯƠNG ĐÃ LƯU", fg="#94a3b8", bg="#111c2e", font=("Segoe UI", 9, "bold")).pack(anchor="w")
		chapter_row = tk.Frame(form, bg="#111c2e")
		chapter_row.pack(fill="x", pady=(6, 12))
		self._button(chapter_row, "Mở chương", self.load_chapter_for_edit).pack(side="right", padx=(8, 0))
		delete_button = self._button(chapter_row, "Xóa chương", self.delete_chapter)
		delete_button.config(bg="#9f1239", activebackground="#be123c")
		delete_button.pack(side="right", padx=(8, 0))
		self.chap_select_combo = ttk.Combobox(chapter_row, font=("Segoe UI", 10), state="readonly", width=20)
		self.chap_select_combo.pack(side="left", fill="x", expand=True)
		meta = tk.Frame(form, bg="#111c2e")
		meta.pack(fill="x", pady=(0, 12))
		meta.columnconfigure(1, weight=1)
		for column, label in enumerate(("ID KẾ TIẾP", "TÊN CHƯƠNG")):
			tk.Label(meta, text=label, bg="#111c2e", fg="#94a3b8", font=("Segoe UI", 9, "bold")).grid(row=0, column=column, sticky="w", pady=(0, 6))
		self.chap_entry = tk.Entry(meta, width=10, bg="#0b1220", fg="#e2e8f0", insertbackground="white", bd=0, font=("Segoe UI", 11))
		self.chap_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12), ipady=8)
		self.chap_title_entry = tk.Entry(meta, bg="#0b1220", fg="#e2e8f0", insertbackground="white", bd=0, font=("Segoe UI", 11))
		self.chap_title_entry.grid(row=1, column=1, sticky="ew", ipady=8)
		setup_entry_shortcuts(self.chap_entry)
		setup_entry_shortcuts(self.chap_title_entry)
		tk.Label(form, text="NỘI DUNG CHƯƠNG", fg="#94a3b8", bg="#111c2e", font=("Segoe UI", 9, "bold")).pack(anchor="w")
		self.content_text = StyledScrolledText(form, height=8, width=30, bg="#0b1220", fg="#e2e8f0",
			insertbackground="white", font=("Segoe UI", 11), wrap=tk.WORD, undo=True,
			bd=0, padx=12, pady=10, spacing1=3, spacing3=5, selectbackground="#115e59")
		self.content_text.pack(fill="both", expand=True, pady=(6, 12))
		setup_text_shortcuts(self.content_text)
		self._button(form, "Lưu chương vào thư viện", self.save_chapter, primary=True).pack(fill="x", pady=(0, 16))

	def build_right(self, parent):
		tk.Label(parent, text="02   Nguồn & phân chương", fg="#f8fafc", bg="#111c2e",
			font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
		tk.Label(parent, text="Mở bản dịch, chọn nội dung hoặc tách thành nhiều chương.",
			fg="#94a3b8", bg="#111c2e", font=("Segoe UI", 10)).pack(anchor="w", padx=18, pady=(0, 12))
		actions = tk.Frame(parent, bg="#111c2e")
		actions.pack(fill="x", padx=18, pady=(0, 10))
		actions.columnconfigure((0, 1), weight=1, uniform="actions")
		for index, (label, command, primary) in enumerate((
			("Mở file JSON", self.pick_json, False),
			("Phân chương tự động", self.open_split_chapters_dialog, True),
			("← Chuyển toàn bộ", self.process_json, False),
			("← Chuyển phần chọn", self.move_selected_text, False))):
			self._button(actions, label, command, primary).grid(row=index//2, column=index%2,
				sticky="ew", padx=(0, 6) if index%2 == 0 else (6, 0), pady=4)
		self.temp_status = tk.Label(parent, text="Chưa mở nguồn · Chọn file JSON để bắt đầu", fg="#94a3b8",
			bg="#111c2e", anchor="w", justify="left", wraplength=440, font=("Segoe UI", 9))
		self.temp_status.pack(fill="x", padx=18, pady=(0, 10))
		parent.bind("<Configure>", lambda e: self.temp_status.config(wraplength=max(200, e.width - 36)), add="+")

		# Sleek search bar (hidden by default)
		self.search_frame = tk.Frame(parent, bg="#25344b", bd=1, relief="solid")
		
		# Elements inside search bar
		tk.Label(self.search_frame, text="🔍 Tìm:", fg="#ffffff", bg="#25344b", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(8, 4))
		
		self.search_entry = tk.Entry(self.search_frame, bg="#0b1220", fg="#ffffff", insertbackground="white", font=("Segoe UI", 9))
		self.search_entry.pack(side="left", fill="x", expand=True, pady=4, padx=4)
		setup_entry_shortcuts(self.search_entry)
		
		self.regex_var = tk.BooleanVar(value=False)
		self.regex_check = tk.Checkbutton(
			self.search_frame,
			text="Regex",
			variable=self.regex_var,
			bg="#25344b",
			fg="#ffffff",
			selectcolor="#0b1220",
			activebackground="#25344b",
			activeforeground="#ffffff",
			font=("Segoe UI", 8),
			command=self.perform_search
		)
		self.regex_check.pack(side="left", padx=4)
		
		self.search_status = tk.Label(self.search_frame, text="0/0", fg="#94a3b8", bg="#25344b", font=("Segoe UI", 8))
		self.search_status.pack(side="left", padx=4)
		
		tk.Button(
			self.search_frame,
			text="←",
			bg="#334155",
			fg="#ffffff",
			command=self.find_prev,
			borderwidth=0,
			padx=6,
			font=("Segoe UI", 8),
			cursor="hand2"
		).pack(side="left", padx=2)
		
		tk.Button(
			self.search_frame,
			text="→",
			bg="#334155",
			fg="#ffffff",
			command=self.find_next,
			borderwidth=0,
			padx=6,
			font=("Segoe UI", 8),
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
			font=("Segoe UI", 8, "bold"),
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
			font=("Segoe UI", 8, "bold"),
			cursor="hand2"
		).pack(side="left", padx=(4, 8))

		# Temp text window
		self.temp_text = StyledScrolledText(
			parent,
			height=10,
			width=30,
			bd=0, padx=12, pady=10, spacing1=3, spacing3=5,
			bg="#0b1220",
			fg="#e4e4e7",
			insertbackground="white",
			font=("Segoe UI", 11),
			wrap=tk.WORD,
			undo=True
		)
		self.temp_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
		setup_text_shortcuts(self.temp_text)
		
		# Configure match tags
		self.temp_text.tag_configure("match", background="#b45309", foreground="#ffffff")
		self.temp_text.tag_configure("active_match", background="#0f766e", foreground="#ffffff")
		
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
				self.story_options = story_options(data)
			except Exception:
				pass

		self.story_combo["values"] = self.story_options
		if hasattr(self, "library_status"):
			self.library_status.config(text=f"{len(self.story_options)} truyện  ·  Mới cập nhật trước")

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

	def get_next_chapter_id(self, story_slug, catalog=None):
		if not story_slug:
			return "000001"

		if catalog is None:
			catalog = self._read_chapter_catalog()

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

	def _read_chapter_catalog(self):
		if os.path.exists(CATALOG_PATH):
			try:
				with open(CATALOG_PATH, "r", encoding="utf-8") as f:
					return json.load(f)
			except Exception:
				pass

		return []

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

	def _refresh_chap_select(self, story_slug, catalog=None, selected_id=None):
		"""Load chapter list for the selected story into chap_select_combo."""
		if catalog is None:
			catalog = self._read_chapter_catalog()

		story = next((item for item in catalog if item.get("slug") == story_slug), None)
		chap_options = []
		if story:
			for chap in story.get("chapters", []):
				cid = chap.get("id", "")
				cname = chap.get("name", "")
				chap_options.append(f"{cid} | {cname}")

		self.chap_select_combo["values"] = chap_options
		selected = next((option for option in chap_options
			if option.split("|", 1)[0].strip() == selected_id), "")
		self.chap_select_combo.set(selected)

	def _sync_saved_chapters(self, story_slug, catalog, selected_id):
		"""Refresh from the catalog just saved, without repeated disk reads."""
		self.story_options = story_options(catalog)
		self.story_combo["values"] = self.story_options
		if hasattr(self, "library_status"):
			self.library_status.config(text=f"{len(self.story_options)} truyện  ·  Mới cập nhật trước")
		selected_story = next((option for option in self.story_options
			if option.split("|", 1)[0].strip() == story_slug), "")
		self.story_combo.set(selected_story)
		self._refresh_chap_select(story_slug, catalog, selected_id)
		self.chap_entry.delete(0, tk.END)
		self.chap_entry.insert(0, self.get_next_chapter_id(story_slug, catalog))



	def delete_story(self):
		"""Delete the selected story and all of its saved chapters."""
		story_value = self.story_combo.get().strip()
		if not story_value or story_value not in self.story_options:
			messagebox.showwarning("Chú ý", "Vui lòng chọn truyện trong danh sách!", parent=self.root)
			return
		story_slug, story_title = (part.strip() for part in story_value.split("|", 1))
		if not messagebox.askyesno(
			"Xóa truyện",
			f"Xóa truyện {story_title} cùng toàn bộ chương đã lưu?\n\n"
			"Dữ liệu truyện sẽ bị xóa khỏi thư viện.",
			parent=self.root, icon="warning", default="no",
		):
			return
		try:
			catalog, cleanup_warning = delete_library_story(story_slug)
		except Exception as error:
			messagebox.showerror("Lỗi", f"Không thể xóa truyện:\n{error}", parent=self.root)
			return

		self.story_options = story_options(catalog)
		self.story_combo["values"] = self.story_options
		self.story_combo.set("")
		self.chap_select_combo["values"] = ()
		self.chap_select_combo.set("")
		self.chap_entry.delete(0, tk.END)
		self.chap_entry.insert(0, "000001")
		self.chap_title_entry.delete(0, tk.END)
		self.content_text.delete("1.0", tk.END)
		if hasattr(self, "library_status"):
			self.library_status.config(text=f"{len(self.story_options)} truyện  ·  Mới cập nhật trước")
		if cleanup_warning:
			messagebox.showwarning("Đã xóa truyện", cleanup_warning, parent=self.root)
		else:
			messagebox.showinfo("Đã xóa truyện", f"Đã xóa truyện: {story_title}", parent=self.root)
	def delete_chapter(self):
		"""Delete the chapter selected in the saved-chapter list."""
		story_value = self.story_combo.get().strip()
		chap_value = self.chap_select_combo.get().strip()
		if not story_value or story_value not in self.story_options:
			messagebox.showwarning("Chú ý", "Vui lòng chọn truyện trong danh sách!", parent=self.root)
			return
		if not chap_value:
			messagebox.showwarning("Chú ý", "Vui lòng chọn chương muốn xóa!", parent=self.root)
			return
		story_slug = story_value.split("|", 1)[0].strip()
		chap_slug = chap_value.split("|", 1)[0].strip()
		if not messagebox.askyesno(
			"Xóa chương",
			f"Xóa chương {chap_value} khỏi truyện {story_value}?\n\n"
			"Dữ liệu chương sẽ bị xóa khỏi thư viện. Nếu đang biên tập chương này, "
			"nội dung chưa lưu cũng sẽ bị xóa.",
			parent=self.root, icon="warning", default="no",
		):
			return
		try:
			catalog, cleanup_warning = delete_library_chapter(story_slug, chap_slug)
		except Exception as error:
			messagebox.showerror("Lỗi", f"Không thể xóa chương:\n{error}", parent=self.root)
			return

		if self.chap_entry.get().strip() == chap_slug:
			self.chap_title_entry.delete(0, tk.END)
			self.content_text.delete("1.0", tk.END)
			self.chap_entry.delete(0, tk.END)
			self.chap_entry.insert(0, self.get_next_chapter_id(story_slug, catalog))
		elif not self.chap_title_entry.get().strip() and not self.content_text.get("1.0", tk.END).strip():
			self.chap_entry.delete(0, tk.END)
			self.chap_entry.insert(0, self.get_next_chapter_id(story_slug, catalog))
		self._refresh_chap_select(story_slug, catalog)
		if cleanup_warning:
			messagebox.showwarning("Đã xóa chương", cleanup_warning, parent=self.root)
		else:
			messagebox.showinfo("Đã xóa chương", f"Đã xóa chương: {chap_value}", parent=self.root)

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
		dialog.configure(bg="#111c2e")

		# Header
		header_frame = tk.Frame(dialog, bg="#0b1220", pady=12)
		header_frame.pack(fill=tk.X)
		tk.Label(
			header_frame,
			text="➕ Thêm Truyện Mới",
			fg="#ffffff",
			bg="#0b1220",
			font=("Segoe UI", 11, "bold"),
		).pack(padx=16, anchor="w")

		# Body
		body_frame = tk.Frame(dialog, bg="#111c2e")
		body_frame.pack(fill=tk.X, padx=16, pady=(14, 0))

		tk.Label(
			body_frame,
			text="Tên hiển thị của truyện:",
			fg="#94a3b8",
			bg="#111c2e",
			font=("Segoe UI", 9),
		).pack(anchor="w")

		entry_var = tk.StringVar(value=default_title)
		entry = tk.Entry(
			body_frame,
			textvariable=entry_var,
			bg="#0b1220",
			fg="#ffffff",
			insertbackground="#ffffff",
			relief="flat",
			font=("Segoe UI", 11),
			bd=0,
			highlightthickness=1,
			highlightbackground="#334155",
			highlightcolor="#0f766e",
		)
		entry.pack(fill=tk.X, pady=(6, 0), ipady=7)
		entry.select_range(0, tk.END)
		entry.focus_set()

		# Hint
		tk.Label(
			body_frame,
			text="ID 4 chữ số sẽ được tạo tự động.",
			fg="#52525b",
			bg="#111c2e",
			font=("Segoe UI", 8),
		).pack(anchor="w", pady=(4, 0))

		# Separator
		tk.Frame(dialog, bg="#25344b", height=1).pack(fill=tk.X, pady=(14, 0))

		# Buttons
		btn_frame = tk.Frame(dialog, bg="#111c2e")
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
			bg="#25344b",
			fg="#94a3b8",
			activebackground="#334155",
			activeforeground="#ffffff",
			relief="flat",
			borderwidth=0,
			padx=18,
			pady=6,
			font=("Segoe UI", 9),
			cursor="hand2",
			command=on_cancel,
		).pack(side=tk.RIGHT, padx=(6, 0))

		tk.Button(
			btn_frame,
			text="✅ Tạo Truyện",
			bg="#0f766e",
			fg="#ffffff",
			activebackground="#059669",
			activeforeground="#ffffff",
			relief="flat",
			borderwidth=0,
			padx=18,
			pady=6,
			font=("Segoe UI", 9, "bold"),
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
		if story_value and story_value not in self.story_options:
			messagebox.showwarning("Chọn truyện", "Hãy chọn một truyện trong danh sách gợi ý trước khi lưu.", parent=self.root)
			return
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

		self._sync_saved_chapters(story_slug, catalog, chap_slug)

		# Dọn dẹp editor và điền sẵn ID chương tiếp theo
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
		self.temp_status.config(text=info_str, fg="#0f766e")

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
		dlg.configure(bg="#0b1220")
		dlg.transient(self.root)
		dlg.grab_set()
		dlg.resizable(True, True)

		# Restore saved geometry
		cfg = load_config()
		geo = cfg.get("editor_split_dialog", "860x640")
		try:
			dlg.geometry(geo)
		except tk.TclError:
			geo = "860x640"
			dlg.geometry(geo)
		dlg.minsize(700, 500)

		resize_timer = None
		restore_timer = None
		restored = False
		closing = False
		normal_geometry = geo
		window_state = cfg.get("editor_split_dialog_state", "normal")
		if window_state not in ("normal", "zoomed"):
			window_state = "normal"

		def capture_dialog_geometry():
			nonlocal normal_geometry, window_state
			if not restored or not dlg.winfo_exists() or not dlg.winfo_ismapped():
				return
			state = dlg.state()
			if state not in ("normal", "zoomed"):
				return
			window_state = state
			if state == "normal" and dlg.winfo_width() >= 700 and dlg.winfo_height() >= 500:
				normal_geometry = dlg.geometry()

		def save_dialog_geometry(capture=True):
			nonlocal resize_timer
			if resize_timer is not None:
				self.root.after_cancel(resize_timer)
			resize_timer = None
			if capture:
				capture_dialog_geometry()
			save_config({
				"editor_split_dialog": normal_geometry,
				"editor_split_dialog_state": window_state,
			})

		def on_dialog_configure(event):
			nonlocal resize_timer, normal_geometry, window_state
			# Child widgets also emit Configure events; only track the dialog.
			if not restored or closing or event.widget is not dlg or event.width < 700 or event.height < 500:
				return
			state = dlg.state()
			if state not in ("normal", "zoomed"):
				return
			window_state = state
			if state == "normal":
				# Configure carries the new size even if wm geometry still lags it.
				position = re.sub(r'^\d+x\d+', '', dlg.geometry())
				normal_geometry = f"{event.width}x{event.height}{position}"
			if resize_timer is not None:
				self.root.after_cancel(resize_timer)
			resize_timer = self.root.after(600, save_dialog_geometry)

		def on_dialog_destroy(event):
			nonlocal resize_timer
			if event.widget is not dlg or closing:
				return
			# Fallback for parent shutdown or a direct destroy(). Tk can no
			# longer be queried here, so use the last Configure snapshot.
			save_dialog_geometry(capture=False)

		destroy_dialog = dlg.destroy

		def on_dlg_close():
			nonlocal closing, restore_timer
			if closing:
				return
			if restore_timer is not None:
				dlg.after_cancel(restore_timer)
				restore_timer = None
			# Save synchronously before destruction, including a recent resize
			# whose debounce timer has not fired yet (X, Cancel and Save All).
			save_dialog_geometry()
			closing = True
			destroy_dialog()

		# Parent shutdown and callers using destroy() must save before Tk
		# discards the window too, not only the title-bar close action.
		dlg.destroy = on_dlg_close
		dlg.bind("<Configure>", on_dialog_configure, add="+")
		dlg.bind("<Destroy>", on_dialog_destroy, add="+")
		dlg.protocol("WM_DELETE_WINDOW", on_dlg_close)
		def restore_dialog_geometry():
			nonlocal restore_timer, restored
			restore_timer = None
			if closing:
				return
			# Desktop window-placement utilities can resize a newly mapped window.
			# Reapply the saved size after that first placement, and never save
			# the temporary startup dimensions as the user's preference.
			dlg.geometry(geo)
			if window_state == "zoomed":
				dlg.state("zoomed")
			dlg.update_idletasks()
			restored = True

		def on_dialog_map(event):
			nonlocal restore_timer
			if event.widget is dlg:
				dlg.unbind("<Map>", map_binding)
				# Allow the desktop's initial placement pass to finish first.
				# On Windows this can arrive well after Map/after_idle (~500 ms).
				restore_timer = dlg.after(1000, restore_dialog_geometry)

		map_binding = dlg.bind("<Map>", on_dialog_map, add="+")

		# ── HEADER ──
		hdr = tk.Frame(dlg, bg="#111c2e", pady=10)
		hdr.pack(fill=tk.X)
		tk.Label(hdr, text="🔪 Phân Chương Tự Động", fg="#ffffff", bg="#111c2e",
				 font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=16)

		# ── STEP 1: Pattern selector ──
		step1 = tk.Frame(dlg, bg="#111c2e", padx=16, pady=8)
		step1.pack(fill=tk.X, padx=12, pady=(8, 0))
		tk.Label(step1, text="BƯỚC 1 — Chọn pattern nhận diện header chương:", fg="#94a3b8",
				 bg="#111c2e", font=("Segoe UI", 9, "bold")).pack(anchor="w")

		pattern_row = tk.Frame(step1, bg="#111c2e")
		pattern_row.pack(fill=tk.X, pady=(6, 0))

		pattern_names = [p[0] for p in patterns]
		pattern_var = tk.StringVar(value=pattern_names[0])
		pattern_combo = ttk.Combobox(pattern_row, textvariable=pattern_var, values=pattern_names,
									 state="readonly", font=("Segoe UI", 9), width=28)
		pattern_combo.pack(side=tk.LEFT, padx=(0, 8))

		regex_var = tk.StringVar(value=patterns[0][1])
		regex_entry = tk.Entry(pattern_row, textvariable=regex_var, bg="#25344b", fg="#e4e4e7",
							   insertbackground="white", font=("Consolas", 9),
							   highlightthickness=1, highlightbackground="#334155",
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

		tk.Button(pattern_row, text="💾 Lưu pattern", bg="#334155", fg="#ffffff",
				  relief="flat", borderwidth=0, padx=8, pady=4, font=("Segoe UI", 8),
				  cursor="hand2", command=save_custom_pattern).pack(side=tk.LEFT, padx=(0, 4))

		# ── Detected chapters state ──
		detected_chapters = []  # list of {"title": str, "paragraphs": [str], "title_var": StringVar}
		chapter_rows_frame = None

		# ── STEP 2: Preview ──
		step2_header = tk.Frame(dlg, bg="#0b1220", padx=16, pady=6)
		step2_header.pack(fill=tk.X, padx=12, pady=(10, 0))
		count_label = tk.Label(step2_header, text="BƯỚC 2 — Xem & chỉnh sửa tên chương:", fg="#94a3b8",
							   bg="#0b1220", font=("Segoe UI", 9, "bold"))
		count_label.pack(side=tk.LEFT)

		tk.Button(step2_header, text="🔍 Phân tích lại", bg="#8b5cf6", fg="#ffffff",
				  relief="flat", borderwidth=0, padx=10, pady=3, font=("Segoe UI", 9, "bold"),
				  cursor="hand2", command=lambda: run_detect()).pack(side=tk.RIGHT)

		# Scrollable list
		list_outer = tk.Frame(dlg, bg="#0b1220")
		list_outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 0))

		canvas = tk.Canvas(list_outer, bg="#0b1220", highlightthickness=0)
		scrollbar = ttk.Scrollbar(list_outer, orient="vertical", style="Editor.Vertical.TScrollbar", command=canvas.yview)
		canvas.configure(yscrollcommand=scrollbar.set)
		scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
		canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

		inner_frame = tk.Frame(canvas, bg="#0b1220")
		canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")

		def on_inner_configure(event):
			canvas.configure(scrollregion=canvas.bbox("all"))
		def on_canvas_configure(event):
			canvas.itemconfig(canvas_window, width=event.width)
		inner_frame.bind("<Configure>", on_inner_configure)
		canvas.bind("<Configure>", on_canvas_configure)

		# Mouse wheel scroll — bind to dlg (not bind_all) so it's removed when dialog closes
		def on_mousewheel(event):
			try:
				canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
			except tk.TclError:
				pass
		dlg.bind("<MouseWheel>", on_mousewheel)

		def build_chapter_list():
			n = len(detected_chapters)
			count_label.config(text=f"BƯỚC 2 — Xem & chỉnh sửa ({n} chương phát hiện):",
				fg="#0f766e" if n else "#ef4444")
			save_btn.config(text=f"💾 Lưu tất cả ({n} chương)")
			for w in inner_frame.winfo_children():
				w.destroy()

			if not detected_chapters:
				tk.Label(inner_frame, text="Không phát hiện được chương nào với pattern này.",
						 fg="#ef4444", bg="#0b1220", font=("Segoe UI", 10)).pack(pady=20)
				return

			# Column headers
			hrow = tk.Frame(inner_frame, bg="#25344b")
			hrow.pack(fill=tk.X, padx=4, pady=(4, 2))
			tk.Label(hrow, text="#", fg="#64748b", bg="#25344b", font=("Segoe UI", 8, "bold"), width=4).pack(side=tk.LEFT, padx=(8,0))
			tk.Label(hrow, text="ID", fg="#64748b", bg="#25344b", font=("Segoe UI", 8, "bold"), width=8).pack(side=tk.LEFT, padx=4)
			tk.Label(hrow, text="Tên chương (có thể sửa)", fg="#64748b", bg="#25344b", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
			tk.Label(hrow, text="Đoạn", fg="#64748b", bg="#25344b", font=("Segoe UI", 8, "bold"), width=6).pack(side=tk.RIGHT, padx=8)

			for i, chap in enumerate(detected_chapters):
				row_bg = "#111c2e" if i % 2 == 0 else "#1c1c1f"
				row = tk.Frame(inner_frame, bg=row_bg)
				row.pack(fill=tk.X, padx=4, pady=1)

				tk.Label(row, text=str(i+1), fg="#52525b", bg=row_bg, font=("Segoe UI", 8), width=4).pack(side=tk.LEFT, padx=(8,0), pady=4)
				tk.Label(row, text=chap["id"], fg="#3b82f6", bg=row_bg, font=("Consolas", 9), width=8).pack(side=tk.LEFT, padx=4)
				tk.Button(row, text="Xóa mốc", command=lambda index=i: remove_boundary(index),
					state=tk.NORMAL if i > 0 else tk.DISABLED,
					bg="#3f2025", fg="#fca5a5", relief="flat", borderwidth=0,
					font=("Segoe UI", 8), padx=6).pack(side=tk.RIGHT, padx=4)

				entry = tk.Entry(row, textvariable=chap["title_var"], bg=row_bg, fg="#e4e4e7",
								 insertbackground="white", font=("Segoe UI", 9), relief="flat",
								 highlightthickness=1, highlightbackground="#25344b",
								 highlightcolor="#8b5cf6")
				entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=4)

				tk.Label(row, text=str(len(chap["paragraphs"])), fg="#0f766e", bg=row_bg,
						 font=("Segoe UI", 8), width=6).pack(side=tk.RIGHT, padx=8)

		def remove_boundary(index):
			if index <= 0 or index >= len(detected_chapters):
				return
			position = canvas.yview()[0]
			removed = detected_chapters.pop(index)
			previous = detected_chapters[index - 1]
			# Restore the original header as body text, not its edited display title.
			if removed["original_title"]:
				previous["paragraphs"].append(removed["original_title"])
			previous["paragraphs"].extend(removed["paragraphs"])
			start = int(detected_chapters[0]["id"])
			for offset, chapter in enumerate(detected_chapters):
				chapter["id"] = f"{start + offset:06d}"
			build_chapter_list()
			canvas.update_idletasks()
			canvas.yview_moveto(position)

		def change_split_story(event=None):
			# Switching the destination must not restore deleted boundaries or titles.
			value = story_combo.get().strip()
			slug = value.split("|", 1)[0].strip() if "|" in value else slugify_vn(value)
			start = int(self.get_next_chapter_id(slug))
			for offset, chapter in enumerate(detected_chapters):
				chapter["id"] = f"{start + offset:06d}"
			build_chapter_list()

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
					"original_title": ch["title"],
					"title_var": tk.StringVar(value=title_val),
					"paragraphs": ch["paragraphs"],
				})

			build_chapter_list()

		# ── STEP 3: Story selector + Save ──
		tk.Frame(dlg, bg="#25344b", height=1).pack(fill=tk.X, padx=12, pady=(8, 0))
		step3 = tk.Frame(dlg, bg="#111c2e", padx=16, pady=10)
		step3.pack(fill=tk.X, padx=12, pady=(0, 0))
		tk.Label(step3, text="BƯỚC 3 — Chọn truyện để lưu:", fg="#94a3b8", bg="#111c2e",
				 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))

		story_row = tk.Frame(step3, bg="#111c2e")
		story_row.pack(fill=tk.X)

		story_combo = StorySearchCombo(story_row, values=self.story_options, font=("Segoe UI", 10),
								   state="readonly")
		# Pre-select current story if available
		cur = self.story_combo.get().strip()
		if cur in self.story_options:
			story_combo.set(cur)
		story_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
		story_combo.bind("<<ComboboxSelected>>", change_split_story, add="+")

		tk.Frame(dlg, bg="#25344b", height=1).pack(fill=tk.X, padx=12)
		btn_row = tk.Frame(dlg, bg="#0b1220", pady=10)
		btn_row.pack(fill=tk.X, padx=12)

		tk.Button(btn_row, text="Hủy", bg="#25344b", fg="#94a3b8", activebackground="#334155",
				  relief="flat", borderwidth=0, padx=16, pady=6, font=("Segoe UI", 9),
				  cursor="hand2", command=on_dlg_close).pack(side=tk.RIGHT, padx=(6, 0))

		save_btn = tk.Button(btn_row, text="💾 Lưu tất cả (0 chương)", bg="#8b5cf6", fg="#ffffff",
				  activebackground="#7c3aed", relief="flat", borderwidth=0,
				  padx=16, pady=6, font=("Segoe UI", 9, "bold"), cursor="hand2",
				  command=lambda: self.save_all_split_chapters(dlg, story_combo, detected_chapters, on_dlg_close))
		save_btn.pack(side=tk.RIGHT)

		# Initial detect
		run_detect()

	def save_all_split_chapters(self, dlg, story_combo, detected_chapters, close_callback):
		"""Save all detected chapters to the library."""
		import datetime
		import shutil

		story_value = story_combo.get().strip()
		if story_value and story_value not in self.story_options:
			messagebox.showwarning("Chọn truyện", "Hãy chọn một truyện trong danh sách gợi ý trước khi lưu.", parent=dlg)
			return
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
		last_saved_id = None
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
			last_saved_id = chap_slug

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

		if saved_count:
			self._sync_saved_chapters(story_slug, catalog, last_saved_id)

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
			self.search_status.config(text="0/0", fg="#94a3b8")
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
		self.search_status.config(text=f"{self.current_match_idx + 1}/{total}", fg="#0f766e")

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
	root.option_add("*TCombobox*Listbox.background", "#0b1220")
	root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
	app = ChapterEditorApp(root)
	root.mainloop()
