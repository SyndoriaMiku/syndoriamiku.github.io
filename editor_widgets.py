"""Shared styling and searchable story selector for the desktop editor."""
import tkinter as tk
from tkinter import ttk, scrolledtext
import unicodedata
from datetime import datetime


def search_key(value):
    value = unicodedata.normalize('NFD', value.casefold().replace('đ', 'd'))
    return ''.join(c for c in value if unicodedata.category(c) != 'Mn')


def story_options(catalog):
    def updated(item):
        try:
            stamp = float(item.get('timestamp') or 0)
            if stamp > 0:
                return stamp
        except (ValueError, TypeError):
            pass
        try:
            return datetime.strptime(item.get('date', ''), '%d/%m/%Y').timestamp()
        except (ValueError, TypeError):
            return 0
    return [f'{item["slug"]} | {item.get("title", "")}'
            for item in sorted(catalog, key=updated, reverse=True) if item.get('slug')]


class StorySearchCombo(ttk.Combobox):
    """Type without losing focus; select a suggestion with arrows/Enter or mouse."""
    def __init__(self, master, **kwargs):
        kwargs['state'] = 'normal'
        super().__init__(master, **kwargs)
        self._popup = None
        self._timer = None
        self._focus_timer = None
        self._matches = []
        self._index = 0
        self._cached_values = None
        self.bind('<KeyRelease>', self._schedule, add='+')
        self.bind('<Down>', lambda e: self._move(1))
        self.bind('<Up>', lambda e: self._move(-1))
        self.bind('<Return>', self._accept)
        self.bind('<Escape>', self._hide)
        self.bind('<FocusOut>', self._schedule_focus_check)
        self.bind('<Button-1>', self._hide, add='+')
        self.bind('<<ComboboxSelected>>', self._hide, add='+')
        self.bind('<<Paste>>', lambda e: self.after_idle(self._show), add='+')
        self.bind('<Destroy>', self._destroy, add='+')

    def _schedule(self, event):
        if event.keysym in ('Up', 'Down', 'Return', 'Escape', 'Tab'):
            return
        if self._timer:
            self.after_cancel(self._timer)
        self._timer = self.after(100, self._show)

    def _show(self):
        self._timer = None
        if not self.winfo_exists() or not self._owns_focus():
            return
        values = tuple(self['values'])
        if values != self._cached_values:
            self._cached_values = values
            self._search_values = [(value, search_key(value)) for value in values]
        words = search_key(self.get()).split()
        self._matches = [v for v, key in self._search_values if all(w in key for w in words)]
        self._index = 0
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.withdraw()
            self._popup.overrideredirect(True)
            self._popup.configure(bg='#3a332c')
            self._list = tk.Listbox(self._popup, bg='#231f1a', fg='#e6dfd2',
                selectbackground='#9c6a28', selectforeground='white',
                font=('Segoe UI', 10), bd=0, highlightthickness=0,
                activestyle='none', exportselection=False, takefocus=False)
            scrollbar = ttk.Scrollbar(self._popup, style='Editor.Vertical.TScrollbar', command=self._list.yview)
            scrollbar.pack(side='right', fill='y', padx=(0, 1), pady=1)
            self._list.configure(yscrollcommand=scrollbar.set)
            self._list.pack(fill='both', expand=True, padx=1, pady=1)
            self._list.bind('<ButtonRelease-1>', self._accept_click)
        self._list.delete(0, 'end')
        # Limit rendered suggestions, keeping the newest matching stories first.
        self._matches = self._matches[:100]
        for value in self._matches or ['Không tìm thấy truyện phù hợp']:
            self._list.insert('end', value)
        self._list.configure(height=min(8, max(1, len(self._matches))))
        if self._matches:
            self._list.selection_set(0)
        self._popup.update_idletasks()
        width = min(max(self.winfo_width(), 460), self.winfo_screenwidth())
        height = self._popup.winfo_reqheight()
        x = max(0, min(self.winfo_rootx(), self.winfo_screenwidth() - width))
        y = self.winfo_rooty() + self.winfo_height() + 3
        if y + height > self.winfo_screenheight():
            y = max(0, self.winfo_rooty() - height - 3)
        self._popup.geometry(f'{width}x{height}+{x}+{y}')
        self._popup.deiconify()
        self._popup.lift()

    def _move(self, direction):
        if self._popup is None or not self._popup.winfo_viewable():
            self._show()
        elif self._matches:
            self._index = (self._index + direction) % len(self._matches)
            self._list.selection_clear(0, 'end')
            self._list.selection_set(self._index)
            self._list.see(self._index)
        return 'break'

    def _accept_click(self, event):
        selected = self._list.curselection()
        if selected:
            self._index = selected[0]
            self._accept()

    def _accept(self, event=None):
        if self._popup is not None and self._popup.winfo_viewable() and self._matches:
            self.set(self._matches[self._index])
            self._hide()
            self.focus_set()
            self.icursor('end')
            self.event_generate('<<ComboboxSelected>>')
        return 'break'

    def _hide(self, event=None):
        if self._timer:
            self.after_cancel(self._timer)
            self._timer = None
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.withdraw()
        return 'break' if event is not None and getattr(event, 'keysym', '') == 'Escape' else None

    def _hide_if_unfocused(self):
        self._focus_timer = None
        if not self.winfo_exists():
            return
        if not self._owns_focus():
            self._hide()

    def _schedule_focus_check(self, event=None):
        if self._focus_timer:
            self.after_cancel(self._focus_timer)
        self._focus_timer = self.after(150, self._hide_if_unfocused)

    def _owns_focus(self):
        """Compare Tcl widget paths without resolving Tk's transient popdown."""
        try:
            focused = str(self.tk.call('focus') or '')
        except tk.TclError:
            return False
        if focused == str(self):
            return True
        return (self._popup is not None and self._popup.winfo_exists()
                and focused.startswith(str(self._popup) + '.'))

    def _destroy(self, event):
        if event.widget is self:
            if self._focus_timer:
                self.after_cancel(self._focus_timer)
                self._focus_timer = None
            self._hide()
            if self._popup is not None and self._popup.winfo_exists():
                self._popup.destroy()


class StyledScrolledText(scrolledtext.ScrolledText):
    """Keep the Text interface while using the editor's themed scrollbar."""
    def __init__(self, master=None, **kwargs):
        kwargs.setdefault('exportselection', False)
        kwargs.setdefault('selectbackground', '#5a4426')
        kwargs.setdefault('selectforeground', '#f4ede1')
        kwargs.setdefault('inactiveselectbackground', '#4a3a22')
        kwargs.setdefault('takefocus', True)
        kwargs.setdefault('highlightthickness', 1)
        kwargs.setdefault('highlightbackground', '#2f2a23')
        kwargs.setdefault('highlightcolor', '#d9a35c')
        super().__init__(master, **kwargs)
        # Khung chứa mặc định nền trắng: khe giữa chữ và thanh cuộn lộ thành vạch trắng.
        self.frame.configure(bg=kwargs.get('bg', kwargs.get('background', '#1e1b17')))
        self.vbar.destroy()
        self.vbar = ttk.Scrollbar(self.frame, orient='vertical',
            style='Editor.Vertical.TScrollbar', command=self.yview)
        self.vbar.pack(side='right', fill='y', before=self._w, padx=(4, 0))
        self.configure(yscrollcommand=self.vbar.set)
        # Keep the Text class bindings for cursor placement and drag selection.
        self.bind('<Button-1>', lambda event: self.focus_set(), add='+')


# Tông màu chung của builder + editor (tối ấm, giống trang web Thư viện).
THEME = {
    'bg': '#15130f', 'panel': '#1e1b17', 'field': '#29251f', 'line': '#3a332c',
    'text': '#e6dfd2', 'strong': '#f4ede1', 'muted': '#a39887', 'accent': '#d9a35c', 'select': '#5a4426',
}


def apply_tk_defaults(root):
    """Mặc định cho widget tk: nút phẳng, hover/bấm cùng tông (thay cho màu xám hệ thống),
    viền ô nhập sáng màu nhấn khi đang gõ. Chỉ áp cho widget không tự đặt các thuộc tính này."""
    t = THEME
    for pattern, value in (
            ('*Button.relief', 'flat'), ('*Button.borderWidth', 0), ('*Button.cursor', 'hand2'),
            ('*Button.activeBackground', t['line']), ('*Button.activeForeground', t['strong']),
            ('*Button.padY', 4), ('*Button.font', ('Segoe UI', 10)),
            ('*Label.font', ('Segoe UI', 10)),
            ('*Checkbutton.activeBackground', t['bg']), ('*Radiobutton.activeBackground', t['bg']),
            ('*Entry.relief', 'flat'), ('*Entry.highlightThickness', 1),
            ('*Entry.highlightBackground', t['line']), ('*Entry.highlightColor', t['accent']),
            ('*Entry.selectBackground', t['select']), ('*Entry.selectForeground', t['strong']),
            ('*Entry.font', ('Segoe UI', 10)),
            ('*Text.selectBackground', t['select']), ('*Text.selectForeground', t['strong']),
            ('*Text.insertBackground', t['strong']), ('*Text.highlightThickness', 0),
            ('*Listbox.selectBackground', t['select']), ('*Listbox.selectForeground', t['strong']),
            ('*Listbox.font', ('Segoe UI', 10)), ('*Listbox.relief', 'flat'),
            ('*Menu.background', t['panel']), ('*Menu.foreground', t['text']),
            ('*Menu.activeBackground', t['select']), ('*Menu.activeForeground', t['strong']),
            ('*Menu.relief', 'flat'), ('*Menu.font', ('Segoe UI', 10)),
            ('*Toplevel.background', t['bg'])):
        root.option_add(pattern, value)
    # Thanh cuộn tối, mảnh (thanh cuộn mặc định của Windows luôn màu trắng).
    style = ttk.Style(root)
    style.theme_use('clam')
    style.layout('Editor.Vertical.TScrollbar', [
        ('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
            ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    style.configure('Editor.Vertical.TScrollbar', background='#4a4238',
        troughcolor=t['panel'], bordercolor=t['panel'], lightcolor='#4a4238',
        darkcolor='#4a4238', borderwidth=0, width=12, arrowsize=12, gripcount=0)
    style.map('Editor.Vertical.TScrollbar', background=[('pressed', '#9c6a28'), ('active', '#5c5347')])


def configure_theme(root):
    apply_tk_defaults(root)
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('TCombobox', fieldbackground='#15130f', background='#2f2a23',
        foreground='#e6dfd2', arrowcolor='#a39887', bordercolor='#4a4238',
        lightcolor='#4a4238', darkcolor='#4a4238', padding=7)
    style.map('TCombobox', fieldbackground=[('readonly', '#15130f')],
        foreground=[('readonly', '#e6dfd2')], selectbackground=[('!disabled', '#d9a35c')])
    style.configure('Vertical.TScrollbar', background='#3a332c', troughcolor='#15130f',
        borderwidth=0, arrowcolor='#a39887')
    style.layout('Editor.Vertical.TScrollbar', [
        ('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
            ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    style.configure('Editor.Vertical.TScrollbar', background='#4a4238',
        troughcolor='#1e1b17', bordercolor='#1e1b17', lightcolor='#4a4238',
        darkcolor='#4a4238', borderwidth=0, width=12, arrowsize=12, gripcount=0)
    style.map('Editor.Vertical.TScrollbar', background=[('pressed', '#9c6a28'), ('active', '#5c5347')])
    root.option_add('*Font', ('Segoe UI', 10))
    root.option_add('*TCombobox*Listbox.background', '#231f1a')
    root.option_add('*TCombobox*Listbox.foreground', '#e6dfd2')
    root.option_add('*TCombobox*Listbox.selectBackground', '#5a4426')
