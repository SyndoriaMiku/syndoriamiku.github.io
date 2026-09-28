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
import library_store as store
from library_store import CatalogError, read_catalog, write_catalog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CATALOG_PATH = os.path.join(LIBRARY_DIR, "list.json")
CONFIG_PATH = os.path.join(BASE_DIR, "editor_config.json")
BACKUP_DIR = os.path.join(BASE_DIR, ".backups")


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
	catalog = read_catalog(CATALOG_PATH)
	story = next((item for item in catalog if item.get("slug") == story_slug), None)
	if story is None or not any(ch.get("id") == chapter_id for ch in story.get("chapters", [])):
		raise ValueError("Chương không còn trong danh mục. Hãy chọn lại chương.")
	if os.path.lexists(chapter_dir) and not os.path.isdir(chapter_dir):
		raise ValueError("Đường dẫn chương không phải thư mục.")

	staging = None
	try:
		if os.path.isdir(chapter_dir):
			staging = tempfile.mkdtemp(prefix=".delete-chapter-", dir=story_dir)
			os.replace(chapter_dir, os.path.join(staging, "chapter"))
		story["chapters"] = [ch for ch in story["chapters"] if ch.get("id") != chapter_id]
		write_catalog(CATALOG_PATH, catalog)
	except Exception:
		if staging:
			staged_chapter = os.path.join(staging, "chapter")
			if os.path.exists(staged_chapter):
				os.replace(staged_chapter, chapter_dir)
			os.rmdir(staging)
		raise

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
	catalog = read_catalog(CATALOG_PATH)
	if not any(item.get("slug") == story_slug for item in catalog):
		raise ValueError("Truyện không còn trong danh mục. Hãy chọn lại truyện.")
	if os.path.lexists(story_dir) and not os.path.isdir(story_dir):
		raise ValueError("Đường dẫn truyện không phải thư mục.")

	staging = None
	try:
		if os.path.isdir(story_dir):
			staging = tempfile.mkdtemp(prefix=".delete-story-", dir=library_root)
			os.replace(story_dir, os.path.join(staging, "story"))
		catalog = [item for item in catalog if item.get("slug") != story_slug]
		write_catalog(CATALOG_PATH, catalog)
	except Exception:
		if staging:
			staged_story = os.path.join(staging, "story")
			if os.path.exists(staged_story):
				os.replace(staged_story, story_dir)
			os.rmdir(staging)
		raise

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
		self._flash_timer = None
		self._count_timer = None
		self._clean_snapshot = ("", "", "")
		self._loaded_chapter = None  # (story_slug, chapter_id) opened with "Mở chương"
		self.search_target = None
		self.current_match_idx = -1

		# Restore saved geometry or use default
		cfg = load_config()
		geo = cfg.get("editor_main", "1300x750")
		self.root.geometry(geo)

		self.setup_ui()
		self.load_story_list()
		self.mark_clean()

		# Save geometry on resize (debounced)
		self.root.bind("<Configure>", self._on_root_configure)
		self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
		for sequence, handler in (("<Control-s>", self.save_chapter), ("<Control-S>", self.save_chapter),
				("<Control-o>", self.pick_json), ("<Control-O>", self.pick_json),
				("<Control-h>", self.show_replace_dialog), ("<Control-H>", self.show_replace_dialog)):
			self.root.bind_all(sequence, lambda event, h=handler: self._main_shortcut(event, h))

	def _main_shortcut(self, event, handler):
		# Shortcuts belong to the main window, not to open dialogs.
		try:
			if event.widget.winfo_toplevel() is not self.root:
				return None
		except (AttributeError, tk.TclError):
			return None
		handler()
		return "break"

	# --- TRẠNG THÁI CHƯA LƯU / THÔNG BÁO NHANH ---

	def _editor_snapshot(self):
		return (self.chap_entry.get().strip(), self.chap_title_entry.get().strip(),
			self.content_text.get("1.0", tk.END).strip())

	def mark_clean(self):
		self._clean_snapshot = self._editor_snapshot()
		self.update_counter()

	def is_dirty(self):
		_chap_id, title, content = self._editor_snapshot()
		clean_title, clean_content = self._clean_snapshot[1], self._clean_snapshot[2]
		# Only unsaved title/content matter; the pre-filled next ID is not user work.
		return (title, content) != (clean_title, clean_content) and bool(title or content)

	def confirm_discard(self, action):
		"""Ask before replacing unsaved editor content. Returns True to continue."""
		if not self.is_dirty():
			return True
		answer = messagebox.askyesnocancel(
			"Nội dung chưa lưu",
			f"Chương đang soạn chưa được lưu.\n\nLưu trước khi {action}?\n"
			"Có = Lưu rồi tiếp tục · Không = Bỏ thay đổi · Hủy = Quay lại",
			parent=self.root, icon="warning")
		if answer is None:
			return False
		if answer:
			return self.save_chapter()
		return True

	def on_app_close(self):
		if self.confirm_discard("thoát"):
			self._save_root_geometry()
			self.root.destroy()

	def flash(self, text, kind="ok"):
		"""Show a non-blocking status message in the footer instead of a popup."""
		colors = {"ok": "#5eead4", "warn": "#fbbf24", "error": "#f87171", "info": "#94a3b8"}
		self.library_status.config(text=text, fg=colors.get(kind, "#94a3b8"))
		if self._flash_timer:
			self.root.after_cancel(self._flash_timer)
		self._flash_timer = self.root.after(8000, self._reset_status)

	def _reset_status(self):
		self._flash_timer = None
		self.library_status.config(text=f"{len(self.story_options)} truyện  ·  Mới cập nhật trước", fg="#94a3b8")

	def schedule_counter(self, event=None):
		if self._count_timer:
			self.root.after_cancel(self._count_timer)
		self._count_timer = self.root.after(300, self.update_counter)

	def update_counter(self):
		self._count_timer = None
		if not hasattr(self, "counter_label"):
			return
		text = self.content_text.get("1.0", tk.END).strip()
		paragraphs = len([p for p in text.split("\n\n") if p.strip()]) if text else 0
		words = len(text.split())
		dirty = "  ·  ● chưa lưu" if self.is_dirty() else ""
		self.counter_label.config(text=f"{words:,} chữ  ·  {paragraphs} đoạn  ·  {len(text):,} ký tự{dirty}".replace(",", "."),
			fg="#fbbf24" if dirty else "#64748b")

	def _on_content_modified(self, event=None):
		if self.content_text.edit_modified():
			self.content_text.edit_modified(False)
			self.schedule_counter()

	def _catalog_or_error(self, parent=None):
		"""Strict read for anything that will write list.json. None on error."""
		try:
			return read_catalog(CATALOG_PATH)
		except CatalogError as error:
			messagebox.showerror("Không đọc được danh mục", f"{error}\n\nĐã dừng để không ghi đè mất danh sách truyện.",
				parent=parent or self.root)
			return None

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
		self.panes = panes
		left = tk.Frame(panes, bg="#111c2e", highlightthickness=1, highlightbackground="#263449")
		right = tk.Frame(panes, bg="#111c2e", highlightthickness=1, highlightbackground="#263449")
		panes.add(left, minsize=460, stretch="always")
		panes.add(right, minsize=460, stretch="always")
		self.build_left(left)
		self.build_right(right)
		self.build_search_bar(self.root)
		footer = tk.Frame(self.root, bg="#0b1220")
		footer.pack(fill="x", padx=24, pady=(0, 12))
		self.library_status = tk.Label(footer, text="Thư viện", bg="#0b1220", fg="#94a3b8", font=("Segoe UI", 9))
		self.library_status.pack(side="left")
		tk.Label(footer, text="Ctrl+S Lưu  •  Ctrl+O Mở JSON  •  Ctrl+F Tìm  •  Ctrl+H Thay thế", bg="#0b1220",
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
		self.chap_select_combo.bind("<Return>", lambda e: self.load_chapter_for_edit())
		self.chap_select_combo.bind("<Double-Button-1>", lambda e: self.load_chapter_for_edit())
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
		content_head = tk.Frame(form, bg="#111c2e")
		content_head.pack(fill="x")
		tk.Label(content_head, text="NỘI DUNG CHƯƠNG", fg="#94a3b8", bg="#111c2e", font=("Segoe UI", 9, "bold")).pack(side="left")
		self.counter_label = tk.Label(content_head, text="", fg="#64748b", bg="#111c2e", font=("Segoe UI", 9))
		self.counter_label.pack(side="right")
		self.content_text = StyledScrolledText(form, height=8, width=30, bg="#0b1220", fg="#e2e8f0",
			insertbackground="white", font=("Segoe UI", 11), wrap=tk.WORD, undo=True,
			bd=0, padx=12, pady=10, spacing1=3, spacing3=5, selectbackground="#115e59")
		self.content_text.pack(fill="both", expand=True, pady=(6, 12))
		setup_text_shortcuts(self.content_text)
		self.content_text.bind("<<Modified>>", self._on_content_modified, add="+")
		self.chap_title_entry.bind("<KeyRelease>", self.schedule_counter, add="+")
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
		
		for widget in (self.temp_text, self.content_text):
			widget.tag_configure("match", background="#b45309", foreground="#ffffff")
			widget.tag_configure("active_match", background="#0f766e", foreground="#ffffff")
			widget.tag_raise("sel")
			widget.bind("<Control-f>", lambda e, w=widget: self.show_search_dialog(target=w))
			widget.bind("<Control-F>", lambda e, w=widget: self.show_search_dialog(target=w))
			widget.bind("<FocusIn>", lambda e, w=widget: self._set_last_text(w), add="+")
			# Tk's Text class maps Ctrl+H to backspace; override it for Replace.
			widget.bind("<Control-h>", lambda e, w=widget: self.show_search_dialog(target=w, replace=True))
			widget.bind("<Control-H>", lambda e, w=widget: self.show_search_dialog(target=w, replace=True))
			# Text's class binding for Ctrl+O inserts a newline; stop it before opening a file.
			widget.bind("<Control-o>", lambda e: (self.pick_json(), "break")[1])
			widget.bind("<Control-O>", lambda e: (self.pick_json(), "break")[1])

	def _set_last_text(self, widget):
		self._last_text = widget

	def build_search_bar(self, parent):
		"""Find/replace bar shared by both text areas (hidden by default)."""
		bar = self.search_frame = tk.Frame(parent, bg="#172338", highlightthickness=1, highlightbackground="#334155")
		label_opts = dict(bg="#172338", fg="#cbd5e1", font=("Segoe UI", 9, "bold"))
		entry_opts = dict(bg="#0b1220", fg="#ffffff", insertbackground="white", font=("Segoe UI", 10), bd=0)
		check_opts = dict(bg="#172338", fg="#e2e8f0", selectcolor="#0b1220", activebackground="#172338",
			activeforeground="#ffffff", font=("Segoe UI", 8))
		small = dict(borderwidth=0, font=("Segoe UI", 8, "bold"), cursor="hand2", fg="#ffffff", padx=8, pady=3)

		row1 = tk.Frame(bar, bg="#172338")
		row1.pack(fill="x", padx=8, pady=(6, 2))
		self.search_where = tk.Label(row1, text="🔍 Tìm:", width=16, anchor="w", **label_opts)
		self.search_where.pack(side="left")
		self.search_entry = tk.Entry(row1, **entry_opts)
		self.search_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=4)
		setup_entry_shortcuts(self.search_entry)
		self.regex_var = tk.BooleanVar(value=False)
		self.case_var = tk.BooleanVar(value=False)
		tk.Checkbutton(row1, text="Regex", variable=self.regex_var, command=self.perform_search, **check_opts).pack(side="left")
		tk.Checkbutton(row1, text="Aa", variable=self.case_var, command=self.perform_search, **check_opts).pack(side="left")
		self.search_status = tk.Label(row1, text="0/0", width=9, fg="#94a3b8", bg="#172338", font=("Segoe UI", 8))
		self.search_status.pack(side="left", padx=4)
		tk.Button(row1, text="←", bg="#334155", command=self.find_prev, **small).pack(side="left", padx=2)
		tk.Button(row1, text="→", bg="#334155", command=self.find_next, **small).pack(side="left", padx=2)
		self.select_above_btn = tk.Button(row1, text="⬆️ Chọn Lên", bg="#8b5cf6", command=self.select_above_match, **small)
		self.select_above_btn.pack(side="left", padx=2)
		self._search_close_btn = tk.Button(row1, text="✕", bg="#ef4444", command=self.hide_search_dialog, **small)
		self._search_close_btn.pack(side="left", padx=(4, 0))

		row2 = self.replace_row = tk.Frame(bar, bg="#172338")
		tk.Label(row2, text="↪ Thay bằng:", width=16, anchor="w", **label_opts).pack(side="left")
		self.replace_entry = tk.Entry(row2, **entry_opts)
		self.replace_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=4)
		setup_entry_shortcuts(self.replace_entry)
		tk.Button(row2, text="Thay", bg="#334155", command=self.replace_current, **small).pack(side="left", padx=2)
		tk.Button(row2, text="Thay tất cả", bg="#0f766e", command=self.replace_all, **small).pack(side="left", padx=2)
		tk.Button(row2, text="Cả truyện…", bg="#b45309", command=self.replace_in_whole_story, **small).pack(side="left", padx=(2, 0))

		self.search_entry.bind("<KeyRelease>", self.schedule_search)
		self.search_entry.bind("<Return>", self.find_next)
		self.search_entry.bind("<Shift-Return>", self.find_prev)
		self.search_entry.bind("<Escape>", self.hide_search_dialog)
		self.replace_entry.bind("<Return>", lambda e: (self.replace_current(), "break")[1])
		self.replace_entry.bind("<Escape>", self.hide_search_dialog)
		for entry in (self.search_entry, self.replace_entry):
			entry.bind("<Control-h>", lambda e: self.show_search_dialog(target=self._target(), replace=True))

	def load_story_list(self):
		self.story_options = []
		os.makedirs(LIBRARY_DIR, exist_ok=True)

		# Auto-migrate list.json from stories/ to library/ if not exists
		if not os.path.exists(CATALOG_PATH):
			old_catalog = os.path.join(BASE_DIR, "stories", "list.json")
			if os.path.exists(old_catalog):
				try:
					shutil.copy2(old_catalog, CATALOG_PATH)
				except Exception:
					pass

		try:
			self.story_options = story_options(read_catalog(CATALOG_PATH))
		except CatalogError as error:
			messagebox.showerror("Không đọc được danh mục",
				f"{error}\n\nTrình biên tập sẽ không ghi vào list.json cho tới khi file được sửa.", parent=self.root)

		self.story_combo["values"] = self.story_options
		if hasattr(self, "library_status"):
			self.library_status.config(text=f"{len(self.story_options)} truyện  ·  Mới cập nhật trước")

	def get_next_story_id(self, catalog=None):
		if catalog is None:
			catalog = self._read_chapter_catalog()
		return store.next_story_id(catalog)

	def get_next_chapter_id(self, story_slug, catalog=None):
		if not story_slug:
			return "000001"
		if catalog is None:
			catalog = self._read_chapter_catalog()
		return store.next_chapter_id(catalog, story_slug)

	def _read_chapter_catalog(self):
		"""Lenient read for display only; writers use _catalog_or_error()."""
		try:
			return read_catalog(CATALOG_PATH)
		except CatalogError:
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
		# Only clear the editor if it holds a chapter of the deleted story.
		if self._loaded_chapter and self._loaded_chapter[0] == story_slug:
			self.chap_title_entry.delete(0, tk.END)
			self.content_text.delete("1.0", tk.END)
			self._loaded_chapter = None
			self.mark_clean()
		if cleanup_warning:
			messagebox.showwarning("Đã xóa truyện", cleanup_warning, parent=self.root)
		else:
			self.flash(f"🗑 Đã xóa truyện: {story_title}")
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
			self._loaded_chapter = None
			self.mark_clean()
		elif not self.chap_title_entry.get().strip() and not self.content_text.get("1.0", tk.END).strip():
			self.chap_entry.delete(0, tk.END)
			self.chap_entry.insert(0, self.get_next_chapter_id(story_slug, catalog))
		self._refresh_chap_select(story_slug, catalog)
		if cleanup_warning:
			messagebox.showwarning("Đã xóa chương", cleanup_warning, parent=self.root)
		else:
			self.flash(f"🗑 Đã xóa chương: {chap_value}")

	def load_chapter_for_edit(self):
		"""Load a chapter from library into the editor for editing."""
		if not self.confirm_discard("mở chương khác"):
			return
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
		self.content_text.edit_reset()
		self._loaded_chapter = (story_slug, chap_slug)
		self.mark_clean()
		self.flash(f"📖 Đang sửa chương {chap_value} — Ctrl+S để lưu đè.", "info")

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


		catalog = self._catalog_or_error()
		if catalog is None:
			return
		# Auto generate 4-digit Story ID
		slug = self.get_next_story_id(catalog)
		if any(item.get('slug') == slug for item in catalog):
			messagebox.showwarning("Chú ý", f"ID/Slug tự động '{slug}' đã tồn tại!")
			return

		store.copy_templates(LIBRARY_DIR, BASE_DIR, slug)
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
			write_catalog(CATALOG_PATH, catalog)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể lưu list.json:\n{e}")
			return

		self.load_story_list()
		self.flash(f"➕ Đã tạo truyện {slug} | {title}  (thư mục library/{slug})")

		# Auto select in combobox
		new_item = f"{slug} | {title}"
		if new_item in self.story_options:
			self.story_combo.set(new_item)
			self.on_story_selected()

	def _chapter_exists(self, catalog, story_slug, chap_slug):
		story = next((item for item in catalog if item.get("slug") == story_slug), None)
		return bool(story) and any(c.get("id") == chap_slug for c in story.get("chapters", []))

	def save_chapter(self):
		"""Save the editor chapter. Returns True when written."""
		story_value = self.story_combo.get().strip()
		if story_value and story_value not in self.story_options:
			messagebox.showwarning("Chọn truyện", "Hãy chọn một truyện trong danh sách gợi ý trước khi lưu.", parent=self.root)
			return False
		chap_slug = self.chap_entry.get().strip()
		chap_title = self.chap_title_entry.get().strip()
		content = self.content_text.get("1.0", tk.END).strip()

		if not story_value:
			messagebox.showwarning("Chú ý", "Vui lòng chọn Truyện!")
			return False
		if not chap_title:
			chap_title = "Oneshot"
		if not content:
			messagebox.showwarning("Chú ý", "Nội dung chương không được để trống!")
			return False

		story_slug, story_title = (part.strip() for part in story_value.split("|", 1))
		catalog = self._catalog_or_error()
		if catalog is None:
			return False

		# Auto assign 6-digit chapter ID if empty
		if not chap_slug:
			chap_slug = self.get_next_chapter_id(story_slug, catalog)
		else:
			chap_slug = slugify_vn(chap_slug)

		# Ghi đè chương có sẵn chỉ khi chính chương đó đang được mở để sửa.
		if (self._chapter_exists(catalog, story_slug, chap_slug)
				and self._loaded_chapter != (story_slug, chap_slug)):
			if not messagebox.askyesno("Ghi đè chương?",
					f"Chương {chap_slug} đã có trong truyện này.\nGhi đè nội dung chương đó?",
					parent=self.root, icon="warning", default="no"):
				return False

		paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
		payload = store.chapter_payload(story_title, chap_title, (("", p) for p in paragraphs))
		try:
			store.write_chapter(LIBRARY_DIR, BASE_DIR, story_slug, chap_slug, payload)
			store.upsert_chapter(catalog, story_slug, story_title, chap_slug, chap_title)
			write_catalog(CATALOG_PATH, catalog)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể lưu chương:\n{e}")
			return False

		self._sync_saved_chapters(story_slug, catalog, chap_slug)

		# Dọn dẹp editor và điền sẵn ID chương tiếp theo
		self.chap_title_entry.delete(0, tk.END)
		self.content_text.delete("1.0", tk.END)
		self.content_text.edit_reset()
		self._loaded_chapter = None
		self.mark_clean()
		self.flash(f"✅ Đã lưu chương {chap_slug} · {chap_title} ({len(paragraphs)} đoạn)")
		return True

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

		# Đang soạn dở thì không đụng vào truyện/ID/tên chương của editor.
		if self.is_dirty():
			detected_story_slug = ""

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
			choice = messagebox.askyesnocancel(
				"Editor đang có nội dung",
				"Có = Viết tiếp xuống dưới\nKhông = Thay thế toàn bộ nội dung đang có\nHủy = Không làm gì",
				parent=self.root,
			)
			if choice is None:
				return
			if choice:
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

	DEFAULT_SPLIT_PATTERNS = store.DEFAULT_SPLIT_PATTERNS

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

		canvas = tk.Canvas(list_outer, bg="#0b1220", highlightthickness=0, height=120)
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

		# ── Xem trước chương + thêm mốc ──
		preview_index = None
		preview_box = tk.Frame(dlg, bg="#111c2e", padx=12, pady=6)
		preview_box.pack(fill=tk.X, padx=12, pady=(6, 0))
		preview_head = tk.Frame(preview_box, bg="#111c2e")
		preview_head.pack(fill=tk.X)
		preview_label = tk.Label(preview_head, text="XEM TRƯỚC — bấm \"Xem\" ở một dòng",
			fg="#94a3b8", bg="#111c2e", font=("Segoe UI", 9, "bold"))
		preview_label.pack(side=tk.LEFT)
		split_btn = tk.Button(preview_head, text="✂ Tách chương tại đoạn có con trỏ", bg="#0f766e", fg="#ffffff",
			relief="flat", borderwidth=0, padx=10, pady=3, font=("Segoe UI", 8, "bold"), cursor="hand2",
			state=tk.DISABLED, command=lambda: split_at_cursor())
		split_btn.pack(side=tk.RIGHT)
		preview_text = tk.Text(preview_box, height=6, wrap=tk.WORD, bg="#0b1220", fg="#cbd5e1",
			insertbackground="white", font=("Segoe UI", 10), bd=0, padx=10, pady=6,
			spacing3=4, cursor="xterm")
		preview_text.pack(fill=tk.X, pady=(6, 0))
		preview_text.tag_configure("para_no", foreground="#64748b", font=("Consolas", 8))
		preview_text.tag_configure("current_para", background="#1e3a4a")
		# Read-only but still clickable: block typing, keep cursor movement.
		preview_text.bind("<Key>", lambda e: None if e.keysym in ("Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End") else "break")

		def paragraph_at_cursor():
			for tag in preview_text.tag_names("insert"):
				if tag.startswith("p_"):
					return int(tag[2:])
			return None

		def highlight_cursor_paragraph(event=None):
			preview_text.tag_remove("current_para", "1.0", tk.END)
			index = paragraph_at_cursor()
			if index is not None:
				ranges = preview_text.tag_ranges(f"p_{index}")
				if ranges:
					preview_text.tag_add("current_para", ranges[0], ranges[1])
		preview_text.bind("<ButtonRelease-1>", highlight_cursor_paragraph, add="+")
		preview_text.bind("<KeyRelease>", highlight_cursor_paragraph, add="+")

		def show_preview(index):
			nonlocal preview_index
			if index is None or index >= len(detected_chapters):
				preview_index = None
				preview_text.delete("1.0", tk.END)
				preview_label.config(text="XEM TRƯỚC — bấm \"Xem\" ở một dòng")
				split_btn.config(state=tk.DISABLED)
				return
			preview_index = index
			chap = detected_chapters[index]
			preview_label.config(text=f"XEM TRƯỚC #{index + 1} · {chap['id']} · {chap['title_var'].get()[:40]}")
			preview_text.delete("1.0", tk.END)
			for number, para in enumerate(chap["paragraphs"]):
				preview_text.insert(tk.END, f"[{number + 1}] ", ("para_no", f"p_{number}"))
				preview_text.insert(tk.END, para + "\n", (f"p_{number}",))
			preview_text.mark_set("insert", "1.0")
			preview_text.yview_moveto(0)
			split_btn.config(state=tk.NORMAL if len(chap["paragraphs"]) > 1 else tk.DISABLED)
			build_chapter_list(keep_scroll=True)

		def renumber():
			if detected_chapters:
				start = int(detected_chapters[0]["id"])
				for offset, chapter in enumerate(detected_chapters):
					chapter["id"] = f"{start + offset:06d}"

		def split_at_cursor():
			if preview_index is None:
				return
			chap = detected_chapters[preview_index]
			index = paragraph_at_cursor()
			if index is None or index == 0:
				messagebox.showinfo("Tách chương", "Đặt con trỏ vào một đoạn (không phải đoạn đầu tiên) để làm tên chương mới.", parent=dlg)
				return
			header = chap["paragraphs"][index]
			new_chapter = {
				"id": chap["id"],
				"original_title": header,
				"title_var": tk.StringVar(value=header[:120]),
				"paragraphs": chap["paragraphs"][index + 1:],
			}
			chap["paragraphs"] = chap["paragraphs"][:index]
			detected_chapters.insert(preview_index + 1, new_chapter)
			renumber()
			show_preview(preview_index + 1)

		def build_chapter_list(keep_scroll=False):
			position = canvas.yview()[0] if keep_scroll else None
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
				row_bg = "#134e4a" if i == preview_index else ("#111c2e" if i % 2 == 0 else "#1c1c1f")
				row = tk.Frame(inner_frame, bg=row_bg)
				row.pack(fill=tk.X, padx=4, pady=1)

				tk.Label(row, text=str(i+1), fg="#52525b", bg=row_bg, font=("Segoe UI", 8), width=4).pack(side=tk.LEFT, padx=(8,0), pady=4)
				tk.Label(row, text=chap["id"], fg="#3b82f6", bg=row_bg, font=("Consolas", 9), width=8).pack(side=tk.LEFT, padx=4)
				tk.Button(row, text="Xem", command=lambda index=i: show_preview(index),
					bg="#25344b", fg="#e2e8f0", relief="flat", borderwidth=0,
					font=("Segoe UI", 8), padx=8, cursor="hand2").pack(side=tk.RIGHT, padx=4)
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

			if position is not None:
				canvas.update_idletasks()
				canvas.yview_moveto(position)

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
			renumber()
			if preview_index is not None and preview_index >= index - 1:
				# The merged chapter (index-1) or a chapter after it shifted up by one.
				show_preview(index - 1 if preview_index <= index else preview_index - 1)
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

			show_preview(None)
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

		catalog = self._catalog_or_error(parent=dlg)
		if catalog is None:
			return
		clashes = [ch["id"] for ch in detected_chapters
			if ch["paragraphs"] and self._chapter_exists(catalog, story_slug, ch["id"])]
		if clashes and not messagebox.askyesno("Ghi đè chương?",
				f"{len(clashes)} chương đã tồn tại ({', '.join(clashes[:5])}...).\nGhi đè các chương này?",
				parent=dlg, icon="warning", default="no"):
			return

		now = datetime.datetime.now()
		saved_count = 0
		last_saved_id = None
		errors = []

		for ch in detected_chapters:
			if not ch["paragraphs"]:
				continue
			chap_slug = ch["id"]
			chap_title = ch["title_var"].get().strip() or f"Chương {chap_slug}"
			payload = store.chapter_payload(story_title, chap_title, (("", p) for p in ch["paragraphs"]))
			try:
				store.write_chapter(LIBRARY_DIR, BASE_DIR, story_slug, chap_slug, payload)
			except Exception as e:
				errors.append(f"{chap_slug}: {e}")
				continue
			store.upsert_chapter(catalog, story_slug, story_title, chap_slug, chap_title, now)
			saved_count += 1
			last_saved_id = chap_slug

		try:
			write_catalog(CATALOG_PATH, catalog)
		except Exception as e:
			messagebox.showerror("Lỗi", f"Không thể cập nhật list.json:\n{e}", parent=dlg)
			return

		if saved_count:
			self._sync_saved_chapters(story_slug, catalog, last_saved_id)

		if errors:
			messagebox.showwarning("Hoàn thành (có lỗi)",
				f"Đã lưu {saved_count}/{len(detected_chapters)} chương.\n\nLỗi:\n" + "\n".join(errors[:5]),
				parent=dlg)
		close_callback()
		if not errors:
			self.flash(f"✅ Đã lưu {saved_count} chương vào truyện '{story_title}'")

	# --- TÌM & THAY THẾ (DÙNG CHUNG CHO 2 Ô VĂN BẢN) ---

	def _target(self):
		return self.search_target or self.temp_text

	def _compiled_query(self):
		query = self.search_entry.get()
		if not query:
			return None
		return store.compile_search(query, regex=self.regex_var.get(), match_case=self.case_var.get())

	def get_match_coords(self):
		ranges = self._target().tag_ranges("match")
		return [(str(ranges[i]), str(ranges[i+1])) for i in range(0, len(ranges), 2)]

	def schedule_search(self, event=None):
		if event is not None and event.keysym in ("Return", "Escape", "Shift_L", "Shift_R"):
			return
		if getattr(self, "_search_timer", None):
			self.root.after_cancel(self._search_timer)
		self._search_timer = self.root.after(300, self.perform_search)

	def _clear_matches(self, widget):
		widget.tag_remove("match", "1.0", tk.END)
		widget.tag_remove("active_match", "1.0", tk.END)

	def perform_search(self, event=None, from_index=None):
		self._search_timer = None
		widget = self._target()
		self._clear_matches(widget)
		self.current_match_idx = -1
		try:
			pattern = self._compiled_query()
		except (re.error, ValueError):
			self.search_status.config(text="Regex lỗi", fg="#ef4444")
			return
		if pattern is None:
			self.search_status.config(text="0/0", fg="#94a3b8")
			return

		text_content = widget.get("1.0", "end-1c")
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
			widget.tag_add("match", *flat_ranges)

		coords = self.get_match_coords()
		if not coords:
			self.search_status.config(text="0/0", fg="#ef4444")
			return
		self.current_match_idx = 0
		if from_index is not None:
			self.current_match_idx = next((i for i, (start, _end) in enumerate(coords)
				if widget.compare(start, ">=", from_index)), 0)
		self.highlight_active_match()

	def highlight_active_match(self):
		widget = self._target()
		widget.tag_remove("active_match", "1.0", tk.END)
		coords = self.get_match_coords()
		if not coords:
			self.current_match_idx = -1
			self.search_status.config(text="0/0", fg="#ef4444")
			return
		self.current_match_idx = max(0, min(self.current_match_idx, len(coords) - 1))
		start, end = coords[self.current_match_idx]
		widget.tag_add("active_match", start, end)
		widget.see(start)
		self.search_status.config(text=f"{self.current_match_idx + 1}/{len(coords)}", fg="#5eead4")

	def find_next(self, event=None):
		widget = self._target()
		coords = self.get_match_coords()
		if not coords:
			return "break"
		active_ranges = widget.tag_ranges("active_match")
		if active_ranges:
			current_pos, op = str(active_ranges[0]), ">"
		else:
			current_pos, op = widget.index(tk.INSERT), ">="
		self.current_match_idx = next((i for i, (start, _end) in enumerate(coords)
			if widget.compare(start, op, current_pos)), 0)
		self.highlight_active_match()
		return "break"

	def find_prev(self, event=None):
		widget = self._target()
		coords = self.get_match_coords()
		if not coords:
			return "break"
		active_ranges = widget.tag_ranges("active_match")
		current_pos = str(active_ranges[0]) if active_ranges else widget.index(tk.INSERT)
		self.current_match_idx = next((i for i in range(len(coords) - 1, -1, -1)
			if widget.compare(coords[i][0], "<", current_pos)), len(coords) - 1)
		self.highlight_active_match()
		return "break"

	def select_above_match(self, event=None):
		widget = self._target()
		coords = self.get_match_coords()
		if not coords or self.current_match_idx < 0 or self.current_match_idx >= len(coords):
			return "break"
		start, _end = coords[self.current_match_idx]
		widget.tag_remove("sel", "1.0", tk.END)
		widget.tag_add("sel", "1.0", start)
		widget.mark_set("insert", "1.0")
		widget.see("1.0")
		widget.focus_set()
		return "break"

	def show_search_dialog(self, event=None, target=None, replace=False):
		target = target or getattr(self, "_last_text", None) or self.temp_text
		if self.search_target is not None and self.search_target is not target:
			self._clear_matches(self.search_target)
		self.search_target = target
		is_source = target is self.temp_text
		self.search_where.config(text="🔍 Tìm trong Nguồn:" if is_source else "🔍 Tìm trong Chương:")
		if is_source:
			self.select_above_btn.pack(side="left", padx=2, before=self._search_close_btn)
		else:
			self.select_above_btn.pack_forget()
		if not self.search_frame.winfo_ismapped():
			self.search_frame.pack(fill="x", padx=24, pady=(0, 10), before=self.panes)
		if replace and not self.replace_row.winfo_ismapped():
			self.replace_row.pack(fill="x", padx=8, pady=(2, 6))
		# Use the current selection as the query when it is a short phrase.
		try:
			selected = target.get("sel.first", "sel.last")
		except tk.TclError:
			selected = ""
		if selected and "\n" not in selected and len(selected) <= 80:
			self.search_entry.delete(0, tk.END)
			self.search_entry.insert(0, selected)
		focus = self.replace_entry if replace and self.search_entry.get() else self.search_entry
		focus.focus_set()
		focus.selection_range(0, tk.END)
		self.perform_search()
		return "break"

	def show_replace_dialog(self, event=None):
		return self.show_search_dialog(replace=True)

	def hide_search_dialog(self, event=None):
		widget = self._target()
		if self.search_frame.winfo_ismapped():
			self.search_frame.pack_forget()
			self.replace_row.pack_forget()
			widget.focus_set()
		self._clear_matches(widget)
		self.current_match_idx = -1
		return "break"

	@staticmethod
	def _edit_as_one_undo(widget, change):
		"""Group delete+insert into a single Ctrl+Z step."""
		auto = widget.cget("autoseparators")
		widget.configure(autoseparators=False)
		try:
			widget.edit_separator()
			change()
			widget.edit_separator()
		finally:
			widget.configure(autoseparators=auto)

	def _replacement_for(self, match):
		replacement = self.replace_entry.get()
		return match.expand(replacement) if self.regex_var.get() else replacement

	def replace_current(self):
		widget = self._target()
		try:
			pattern = self._compiled_query()
		except (re.error, ValueError) as error:
			self.flash(f"Regex lỗi: {error}", "error")
			return
		active = widget.tag_ranges("active_match")
		if pattern is None or not active:
			self.perform_search()
			return
		start, end = str(active[0]), str(active[1])
		offset = len(widget.get("1.0", start))
		match = pattern.match(widget.get("1.0", "end-1c"), offset)
		if not match:
			self.perform_search()
			return
		try:
			new_text = self._replacement_for(match)
		except (re.error, IndexError) as error:
			self.flash(f"Chuỗi thay thế lỗi: {error}", "error")
			return
		self._edit_as_one_undo(widget, lambda: (widget.delete(start, end), widget.insert(start, new_text)))
		self.perform_search(from_index=f"{start}+{len(new_text)}c")

	def replace_all(self):
		widget = self._target()
		try:
			pattern = self._compiled_query()
			if pattern is None:
				return
			text = widget.get("1.0", "end-1c")
			new_text, count = pattern.subn(self._replacement_for, text)
		except (re.error, IndexError, ValueError) as error:
			self.flash(f"Lỗi thay thế: {error}", "error")
			return
		if not count:
			self.flash("Không có chỗ nào khớp để thay.", "warn")
			return
		self._edit_as_one_undo(widget, lambda: (widget.delete("1.0", "end-1c"), widget.insert("1.0", new_text)))
		self.perform_search()
		self.flash(f"↪ Đã thay {count} chỗ trong {'Nguồn' if widget is self.temp_text else 'Chương'} (Ctrl+Z để hoàn tác).")

	def replace_in_whole_story(self):
		"""Replace in every saved chapter of the selected story (with backup)."""
		story_value = self.story_combo.get().strip()
		if story_value not in self.story_options:
			messagebox.showwarning("Chọn truyện", "Chọn truyện ở ô TRUYỆN bên trái trước.", parent=self.root)
			return
		story_slug, story_title = (part.strip() for part in story_value.split("|", 1))
		try:
			pattern = self._compiled_query()
		except (re.error, ValueError) as error:
			messagebox.showerror("Regex lỗi", str(error), parent=self.root)
			return
		if pattern is None:
			messagebox.showwarning("Chú ý", "Nhập nội dung cần tìm trước.", parent=self.root)
			return
		if self._loaded_chapter and self._loaded_chapter[0] == story_slug and self.is_dirty():
			messagebox.showwarning("Chương chưa lưu",
				"Chương của truyện này đang mở và chưa lưu. Hãy lưu (Ctrl+S) hoặc bỏ thay đổi trước.", parent=self.root)
			return
		catalog = self._catalog_or_error()
		if catalog is None:
			return
		replacement = self.replace_entry.get()
		regex = self.regex_var.get()
		try:
			preview = store.replace_in_story(LIBRARY_DIR, catalog, story_slug, pattern, replacement, regex=regex)
		except Exception as error:
			messagebox.showerror("Lỗi", f"Không quét được truyện:\n{error}", parent=self.root)
			return
		if not preview["total"]:
			self.flash(f"Không tìm thấy \"{self.search_entry.get()}\" trong truyện {story_title}.", "warn")
			return
		sample = ", ".join(f"{cid} ({n})" for cid, n in preview["chapters"][:8])
		more = "…" if len(preview["chapters"]) > 8 else ""
		if not messagebox.askyesno("Thay trong cả truyện",
				f"Thay {preview['total']} chỗ trong {len(preview['chapters'])} chương của \"{story_title}\"?\n\n"
				f"\"{self.search_entry.get()}\" → \"{replacement}\"\n\nChương: {sample}{more}\n\n"
				"Bản data.json cũ được sao lưu vào thư mục .backups.",
				parent=self.root, icon="warning", default="no"):
			return
		try:
			result = store.replace_in_story(LIBRARY_DIR, catalog, story_slug, pattern, replacement,
				regex=regex, apply=True, backup_root=BACKUP_DIR)
			write_catalog(CATALOG_PATH, catalog)
		except Exception as error:
			messagebox.showerror("Lỗi", f"Thay thế bị dừng giữa chừng:\n{error}\n\nBản sao lưu nằm trong {BACKUP_DIR}.",
				parent=self.root)
			return

		# The open chapter (clean) now differs from disk: apply the same change to it.
		if self._loaded_chapter and self._loaded_chapter[0] == story_slug:
			changed_ids = {cid for cid, _n in result["chapters"]}
			if self._loaded_chapter[1] in changed_ids:
				body = self.content_text.get("1.0", "end-1c")
				new_body = pattern.sub(self._replacement_for, body)
				self.content_text.delete("1.0", tk.END)
				self.content_text.insert("1.0", new_body)
				title = self.chap_title_entry.get()
				self.chap_title_entry.delete(0, tk.END)
				self.chap_title_entry.insert(0, pattern.sub(self._replacement_for, title))
				self.mark_clean()
		current = self.chap_select_combo.get().split("|", 1)[0].strip() or None
		self._refresh_chap_select(story_slug, catalog, current)
		self.perform_search()
		self.flash(f"↪ Đã thay {result['total']} chỗ trong {len(result['chapters'])} chương · sao lưu: {result['backup']}")


if __name__ == "__main__":
	root = tk.Tk()
	style = ttk.Style()
	style.theme_use("clam")
	root.option_add("*TCombobox*Listbox.background", "#0b1220")
	root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
	app = ChapterEditorApp(root)
	root.mainloop()
