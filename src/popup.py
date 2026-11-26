# -*- coding: utf-8 -*-
"""小窗：镜像中文 → 语言下拉 → 翻译 → 整段替换。全程 WS_EX_NOACTIVATE。"""
import ctypes
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 128
WS_EX_NOACTIVATE = 134217728

BG, HEAD, TXT, MUTED = '#1e1f22', '#2b5cd6', '#e8e8e8', '#9aa0a6'
FIELD, GREEN, BLUE, GRAY = '#2a2b2f', '#1f9d55', '#2f6fed', '#555a63'


class Popup:
    def __init__(self, root, cfg, handlers):
        self.cfg, self.handlers = cfg, handlers
        self.visible = False
        self.blind = False
        top = tk.Toplevel(root)
        self.top = top
        top.withdraw()
        top.overrideredirect(True)
        top.geometry(f'{cfg.popup_width}x{cfg.popup_height}+100+100')
        top.configure(bg=BG)
        top.attributes('-topmost', cfg.topmost)
        top.protocol('WM_DELETE_WINDOW', self.hide)

        fam = 'Microsoft YaHei UI'
        self.f_s = tkfont.Font(family=fam, size=9)
        self.f_b = tkfont.Font(family=fam, size=11)
        self.f_bb = tkfont.Font(family=fam, size=11, weight='bold')
        self.f_en = tkfont.Font(family='Segoe UI', size=11)

        self._style()

        head = tk.Frame(top, bg=HEAD, height=26)
        head.pack(fill='x')
        self.lbl_title = tk.Label(head, text='输入翻译桥 · 实时镜像', bg=HEAD, fg='white',
                                  font=self.f_bb)
        self.lbl_title.pack(side='left', padx=8)
        tk.Label(head, text='✕', bg=HEAD, fg='#dcdcdc', font=self.f_b,
                 cursor='hand2').pack(side='right', padx=8)
        head.bind('<B1-Motion>', self._drag)
        self.lbl_title.bind('<B1-Motion>', self._drag)

        box = tk.Frame(top, bg=BG)
        box.pack(fill='both', expand=True, padx=8, pady=(6, 2))
        self.lbl_hint = tk.Label(box, text='你输入的中文（讯飞上屏后实时镜像）', bg=BG, fg=MUTED,
                                 font=self.f_s, justify='left')
        self.lbl_hint.pack(anchor='w')
        self.txt = tk.Text(box, height=4, wrap='word', bg=FIELD, fg=TXT, relief='flat', bd=0,
                           font=self.f_b, insertbackground=TXT, selectbackground='#4a6fd8',
                           state='disabled')
        self.txt.pack(fill='both', expand=True, pady=(2, 0))

        rf = tk.Frame(top, bg=BG)
        rf.pack(fill='both', expand=True, padx=8, pady=2)
        tk.Label(rf, text='译文', bg=BG, fg=MUTED, font=self.f_s).pack(anchor='w')
        self.res = tk.Text(rf, height=3, wrap='word', bg='#233043', fg='#dceaff', relief='flat',
                           bd=0, font=self.f_en, selectbackground='#4a6fd8', state='disabled')
        self.res.pack(fill='both', expand=True, pady=(2, 0))

        self.action = tk.Frame(top, bg=BG)

        self.lang_var = tk.StringVar(value=cfg.target_lang)
        self._languages = []
        self._picker = None
        self._picker_rows = []
        self.lang_btn = tk.Button(self.action, relief='flat', bg=FIELD, fg=TXT,
                                  activebackground=BLUE, activeforeground='white',
                                  font=self.f_s, padx=6, highlightthickness=0, bd=0,
                                  command=self.open_lang_picker)
        self.lang_btn.pack(side='left')
        self.set_languages(list(getattr(cfg, 'languages', []) or []))
        self.lang_var.trace_add('write', lambda *_: self._sync_lang_text())
        tk.Label(self.action, text='→', bg=BG, fg=MUTED, font=self.f_s).pack(side='left', padx=3)

        self.auto_var = tk.BooleanVar(value=bool(cfg.auto_retranslate))
        self.chk = tk.Checkbutton(self.action, text='自动重译', variable=self.auto_var, bg=BG,
                                  fg=TXT, selectcolor=FIELD, activebackground=BG,
                                  activeforeground=TXT, font=self.f_s, highlightthickness=0,
                                  bd=0, command=self._on_auto)
        self.chk.pack(side='left', padx=(2, 6))
        self._btn(self.action, '翻译', GREEN, lambda: self._fire('translate'))
        self._btn(self.action, '替换输入框', BLUE, lambda: self._fire('replace'))
        self._btn(self.action, '复制', GRAY, lambda: self._fire('copy'))
        self._btn(self.action, '关闭', GRAY, lambda: self._fire('close'))
        self.action.pack(fill='x', padx=8, pady=(2, 2))
        self.action.pack_forget()

        self.undo_row = tk.Frame(top, bg=BG)
        self._btn(self.undo_row, '撤销替换', '#8a5a2b', lambda: self._fire('undo'))
        self._btn(self.undo_row, '恢复中文原文', '#555a63', lambda: self._fire('restore_cn'))
        self._btn(self.undo_row, '关闭', GRAY, lambda: self._fire('close'))
        self.lbl_hist = tk.Label(self.undo_row, text='', bg=BG, fg=MUTED, font=self.f_s)
        self.lbl_hist.pack(side='left')
        self.undo_row.pack(fill='x', padx=8, pady=(0, 2))
        self.undo_row.pack_forget()

        self.hotkey_text = getattr(cfg, 'hotkey_translate', '') or 'ctrl+alt+shift+t'
        self.blind_row = tk.Frame(top, bg=BG)
        self.btn_grab = self._btn(self.blind_row, self._grab_label(), '#8a5a2b',
                                  lambda: self._fire('grab'))
        self.blind_row.pack(fill='x', padx=8, pady=(2, 0))
        self.blind_row.pack_forget()

        foot = tk.Frame(top, bg=BG)
        foot.pack(fill='x', padx=8, pady=(0, 8))
        self.lbl_count = tk.Label(foot, text='0 / 300', bg=BG, fg=MUTED, font=self.f_s)
        self.lbl_count.pack(side='left')
        self.lbl_status = tk.Label(foot, text='', bg=BG, fg=MUTED, font=self.f_s)
        self.lbl_status.pack(side='right')

        top.after(50, self._apply_exstyle)

    def _style(self):
        st = ttk.Style(self.top)
        try:
            st.theme_use('clam')
        except Exception:
            pass
        st.configure('Dark.TCombobox', fieldbackground=FIELD, background=FIELD,
                     foreground=TXT, arrowcolor=TXT, borderwidth=0, relief='flat')
        st.map('Dark.TCombobox', fieldbackground=[('readonly', FIELD)])
        self.top.option_add('*TCombobox*List.background', FIELD)
        self.top.option_add('*TCombobox*List.foreground', TXT)
        self.top.option_add('*TCombobox*List.selectBackground', '#4a6fd8')

    def _btn(self, parent, text, color, cmd, side='right'):
        b = tk.Button(parent, text=text, bg=color, fg='white', relief='flat', bd=0,
                      padx=9, pady=3, font=self.f_s, cursor='hand2',
                      activebackground='#3f83f8', activeforeground='white', command=cmd)
        b.pack(side=side, padx=(4, 0))
        return b

    def _fire(self, k):
        fn = self.handlers.get(k)
        if fn:
            fn()

    def _on_lang(self, _=None):
        self.cfg.target_lang = self.lang_var.get()
        self._fire('lang')

    def set_languages(self, langs):
        """重灌语言列表。设置窗口保存后由 refresh_actions / main 调用。"""
        langs = [str(x) for x in (langs or []) if str(x).strip()]
        self._languages = langs
        self._close_picker()
        self._sync_lang_text()

    def select_lang(self, name: str):
        """列表点选 = 用户选了目标语言：写入 cfg 并触发 lang 回调（自动重译走原链路）。"""
        name = str(name or '').strip()
        if not name:
            return
        self.lang_var.set(name)
        self._on_lang()
        self._sync_lang_text()

    def _picker_alive(self) -> bool:
        if self._picker is None:
            return False
        try:
            return bool(self._picker.winfo_exists())
        except Exception:
            return False

    def _close_picker(self):
        if self._picker is not None:
            try:
                self._picker.destroy()
            except Exception:
                pass
        self._picker = None
        self._picker_rows = []

    def open_lang_picker(self):
        """点语言按钮弹/收语言列表。列表窗和主小窗同款 exstyle（不抢焦点、不占任务栏），
        点一行 = 选语言并收起；再点按钮 = 收起；主窗隐藏时同步收起。"""
        if self._picker_alive():
            self._close_picker()
            return
        cur = self.lang_var.get()
        win = tk.Toplevel(self.top)
        self._picker = win
        win.overrideredirect(True)
        win.configure(bg=FIELD)
        win.attributes('-topmost', True)

        head = tk.Frame(win, bg=HEAD)
        head.pack(fill='x')
        tk.Label(head, text='选择目标语言', bg=HEAD, fg='white',
                 font=self.f_s).pack(side='left', padx=6, pady=1)
        x_btn = tk.Label(head, text='✕', bg=HEAD, fg='#dcdcdc', font=self.f_s,
                         cursor='hand2')
        x_btn.pack(side='right', padx=6)
        x_btn.bind('<Button-1>', lambda e: self._close_picker())

        self._picker_rows = []
        for name in (self._languages or []):
            cmd = lambda n=name: (self.select_lang(n), self._close_picker())
            lbl = tk.Label(win, text=('✓ ' if name == cur else '   ') + name, bg=FIELD, fg=TXT,
                           font=self.f_s, anchor='w', padx=8, pady=2, cursor='hand2')
            lbl.pack(fill='x')
            lbl.bind('<Button-1>', lambda e, c=cmd: c())
            lbl.bind('<Enter>', lambda e, w=lbl: w.configure(bg='#4a6fd8'))
            lbl.bind('<Leave>', lambda e, w=lbl: w.configure(bg=FIELD))
            self._picker_rows.append((lbl, name, cmd))
        if not self._picker_rows:
            tk.Label(win, text='（语言列表为空，去设置窗口添加）', bg=FIELD,
                     fg=MUTED, font=self.f_s, padx=8, pady=4).pack(anchor='w')

        win.update_idletasks()
        bw, bh = win.winfo_reqwidth(), win.winfo_reqheight()
        bx, by = self.lang_btn.winfo_rootx(), self.lang_btn.winfo_rooty()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w = max(bw, 110)
        x = max(0, min(bx, sw - w - 4))
        y = by - bh - 2
        if y < 0:
            y = min(by + self.lang_btn.winfo_height() + 2, sh - bh - 4)
        win.geometry('%dx%d+%d+%d' % (w, bh, x, y))

        def _style():
            try:
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
                s = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                                    s | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
            except Exception:
                win.after(120, _style)
        try:
            win.update_idletasks()
        except Exception:
            pass
        _style()
        win.after(60, _style)

    def _sync_lang_text(self):
        try:
            self.lang_btn.configure(text='%s ▾' % (self.lang_var.get() or '译'))
        except Exception:
            pass

    def _on_auto(self):
        self._fire('auto')

    def show_undo_row(self, show: bool, hist: str = ''):
        try:
            if show:
                self.lbl_hist.configure(text=hist)
                if not self.undo_row.winfo_manager():
                    self.undo_row.pack(fill='x', padx=8, pady=(0, 2))
            elif self.undo_row.winfo_manager():
                self.undo_row.pack_forget()
            self._fit_height()
        except Exception:
            pass

    def _grab_label(self) -> str:
        return '抓取输入框  %s' % self.hotkey_text.upper()

    def _fit_height(self):
        try:
            self.top.update_idletasks()
            w = int(self.cfg.popup_width)
            need = int(self.top.winfo_reqheight())
            sw, sh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
            h = max(int(self.cfg.popup_height), need)
            h = max(120, min(h, max(120, sh - 8)))
            x, y = self.top.winfo_x(), self.top.winfo_y()
            x = max(0, min(x, sw - w - 6))
            y = max(0, min(y, sh - h - 6))
            self.top.geometry(f'{w}x{h}+{x}+{y}')
            self.top.update_idletasks()
        except Exception:
            pass

    def _find_btn(self, parent, keyword: str):
        try:
            for ch in parent.winfo_children():
                if isinstance(ch, tk.Button) and keyword in str(ch.cget('text')):
                    return ch
        except Exception:
            pass
        return None

    def button_alloc_height(self, keyword: str = '替换') -> int:
        """按钮实际拿到的像素高度；1~10 这种值就是被窗口裁掉了。"""
        b = self._find_btn(self.action, keyword)
        if b is None:
            return 0
        try:
            self.top.update_idletasks()
            return int(b.winfo_height())
        except Exception:
            return 0

    def button_clickable(self, keyword: str = '替换') -> bool:
        """按钮既要有可点的高度，也要整颗落在窗口可视区里。

        纵向被裁（窗口高度写死）和横向被挤（一行里控件太多）是同一类缺陷的
        两个方向，两个方向都要判，只判纵向会放过「关闭」那种被挤扁的按钮。
        """
        b = self._find_btn(self.action, keyword)
        if b is None:
            return False
        try:
            self.top.update_idletasks()
            h = int(b.winfo_height())
            w = int(b.winfo_width())
            bottom = int(self.action.winfo_y()) + int(b.winfo_y()) + h
            right = int(self.action.winfo_x()) + int(b.winfo_x()) + w
            return (h >= 18 and w >= 20
                    and bottom <= int(self.top.winfo_height())
                    and right <= int(self.top.winfo_width()))
        except Exception:
            return False

    def set_hotkey_text(self, text: str) -> None:
        """主程序注册成功后把生效热键喂进来，界面上教的键必须就是能按的那个。"""
        text = (text or '').strip()
        if not text or text == self.hotkey_text:
            return
        self.hotkey_text = text
        try:
            self.btn_grab.configure(text=self._grab_label())
            if self.blind:
                self.lbl_hint.configure(text=self._blind_hint())
            self._fit_height()
        except Exception:
            pass

    def _blind_hint(self, app: str = '') -> str:
        return (f'「{app or getattr(self, "blind_app", "") or "该程序"}」'
                '无无障碍接口，读不到实时输入。\n光标进输入框后按 '
                f'{self.hotkey_text.upper()} 抓取并翻译，被占用时点下面的按钮。')

    def refresh_actions(self):
        """设置窗口保存后调用：语言列表与热键文字同步到界面上。"""
        try:
            self.set_languages(list(self.cfg.languages))
            self.lang_var.set(self.cfg.target_lang)
            self.btn_grab.configure(text=self._grab_label())
            if self.blind:
                self.lbl_hint.configure(text=self._blind_hint())
        except Exception:
            pass

    def set_blind_mode(self, on: bool, app: str = ''):
        """盲应用（零无障碍的自绘程序，如微信 4.x）：换标题、给提示、露出抓取按钮。"""
        on = bool(on)
        if app:
            self.blind_app = app
        if on == getattr(self, 'blind', None):
            return
        self.blind = on
        try:
            if on:
                self.lbl_title.configure(text='输入翻译桥 · 抓取模式')
                self.lbl_hint.configure(text=self._blind_hint(app))
                if not self.blind_row.winfo_manager():
                    self.blind_row.pack(fill='x', padx=8, pady=(2, 0))
            else:
                self.lbl_title.configure(text='输入翻译桥 · 实时镜像')
                self.lbl_hint.configure(text='你输入的中文（讯飞上屏后实时镜像）')
                if self.blind_row.winfo_manager():
                    self.blind_row.pack_forget()
            self._fit_height()
        except Exception:
            pass

    def auto_retranslate(self) -> bool:
        return bool(self.auto_var.get())

    def _apply_exstyle(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id()) or self.top.winfo_id()
            s = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                                s | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        except Exception:
            self.top.after(150, self._apply_exstyle)

    def _drag(self, ev):
        self.top.geometry(f'+{ev.x_root - 60}+{ev.y_root - 12}')

    def show(self, x=None, y=None):
        if not self.visible:
            self.top.deiconify()
            self.visible = True
        self._apply_exstyle()
        if x is not None and y is not None:
            w, h = self.cfg.popup_width, self.cfg.popup_height
            sw, sh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
            x = max(0, min(int(x), sw - w - 6))
            y = max(0, min(int(y), sh - h - 6))
            self.top.geometry(f'{w}x{h}+{x}+{y}')
        self._fit_height()
        self.top.attributes('-topmost', self.cfg.topmost)

    def hide(self):
        if self.visible:
            self.top.withdraw()
            self.visible = False
        self.show_actions(False)
        self.show_undo_row(False)
        self._close_picker()

    def set_text(self, text: str):
        self.txt.configure(state='normal')
        self.txt.delete('1.0', 'end')
        self.txt.insert('1.0', text)
        self.txt.configure(state='disabled')
        n = len(text.rstrip())
        mx = self.cfg.max_chars
        self.lbl_count.configure(text=f'{n} / {mx}', fg='#ff6b6b' if n > mx else MUTED)

    def set_result(self, t: str):
        self.res.configure(state='normal')
        self.res.delete('1.0', 'end')
        self.res.insert('1.0', t)
        self.res.configure(state='disabled')

    def clear_result(self):
        self.set_result('')

    def set_status(self, msg, color=MUTED):
        self.lbl_status.configure(text=msg, fg=color)

    def show_actions(self, show: bool):
        try:
            if show:
                if not self.action.winfo_manager():
                    self.action.pack(fill='x', padx=8, pady=(2, 8))
            elif self.action.winfo_manager():
                self.action.pack_forget()
            self._fit_height()
        except Exception:
            pass

    def target_lang(self) -> str:
        return self.lang_var.get() or '英文'

    def current_result(self) -> str:
        return self.res.get('1.0', 'end').strip()
