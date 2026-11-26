# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'seltrans.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""v2.5 功能③：划词翻译 —— 悬浮小窗 + 纯判定函数。\n\n两条触发通道（能力差异是实测出来的，不是设计偏好）：\n- **自动**：UIA 暴露选区的程序（浏览器网页、Electron/Cherry Studio、QQNT 新版QQ、\n  Word/WPS、记事本…）→ `text_io.get_selection_text()` 非入侵读取，划词即译。\n- **热键**：零无障碍的自绘程序（微信 4.x、旧QQ）→ UIA 读不到，按第 5 把热键后\n  降级为 `grab_selection()`：只发 Ctrl+C 复制**用户已划好的选区**（不发 Ctrl+A），\n  读完 1.2 秒还原剪贴板。\n\n窗体和主小窗一样是 WS_EX_NOACTIVATE + overrideredirect：弹出时不抢键盘焦点，\n用户划完词接着打字不受打断；按钮点击不需要窗口激活（tk.Button 在 NOACTIVATE 窗\n里可用——不可用的是要焦点的下拉列表）。\n\nv2.5.2：**窗内自带两个独立语言选框（源 → 目标）**。划词的原文未必是中文——\n网页/微信里大段英文、俄文都常见，只给一个目标语言框就永远只能\"中文→X\"。\n两个选框照 R27 定案的自绘列表窗做（普通 tk.Label 点击，NOACTIVATE+TOOLWINDOW），\n点中与对面相同的语言时两侧自动互换，两次点击就能拼出「英 → 中」「中 → 葡」。\n"""
import ctypes
import re
import tkinter as tk
from tkinter import font as tkfont
GWL_EXSTYLE = (-20)
WS_EX_TOOLWINDOW = 128
WS_EX_NOACTIVATE = 134217728
BG, HEAD, TXT, MUTED = ('#1e1f22', '#2b5cd6', '#e8e8e8', '#9aa0a6')
FIELD, GREEN, BLUE, GRAY, YELLOW, RED = ('#2a2b2f', '#1f9d55', '#2f6fed', '#555a63', '#ffd166', '#ff6b6b')
_HAS_WORD = re.compile('[A-Za-z一-鿿À-ɏЀ-ӿ؀-ۿ฀-๿]')
def source_language_options(langs) -> list:
    """源语言选框的列表：中文永远排第一（划词最常见方向），其余按目标语言表顺序。\n    去重；langs 为空时退回默认的几个常用源。"""
    out = ['中文']
    for x in langs or []:
        x = str(x).strip()
        if x and x not in out:
                out.append(x)
    if len(out) == 1:
        out += ['英文', '日文', '韩文']
    return out
def direction_needs_translation(src: str, tgt: str) -> bool:
    """源=目标（或目标为空）时不发起请求：自己译自己没有意义，还白占一次推理。"""
    return bool(tgt) and (src or '中文') != tgt
def apply_direction_pick(cur_src, cur_tgt, side, new):
    """双选框点选的纯函数。side ∈ {\"src\",\"tgt\"}。\n\n    规则（都是为了让\"改方向\"变成一次点击）：\n    - 空选择 = 不动；\n    - 选中的语言和**对面**相同 → 两侧互换：「中文→英文」时点源=英文，直接得到\n      「英文→中文」，而不是出现「英文→英文」这种自己译自己的死方向；\n    - 其余情况：只改被点的那一侧。\n    """
    new = str(new or '').strip()
    if not new:
        return (cur_src, cur_tgt)
    else:
        if side == 'src':
            if new == cur_tgt:
                return (new, cur_src)
            else:
                return (new, cur_tgt)
        else:
            if new == cur_src:
                return (cur_tgt, new)
            else:
                return (cur_src, new)
def selection_should_translate(sel: str, cfg, translated: str='', mirror: str='') -> bool:
    """纯函数：这个选区值不值得自动翻译。不碰系统、不起线程，单元测试好喂。\n\n    自动通道只有这一道闸门，必须挡住三类误触发：\n    ① 用户拖拽划中整页（>sel_max_chars 不弹，防刷屏防把模型打爆）；\n    ② 选中的是数字/符号串；\n    ③ 选区恰好等于我们刚写回的译文或镜像里的原文——否则\"写回→全选残留→再翻译\"会自循环。\n    """
    s = (sel or '').strip()
    if not s:
        return False
    else:
        try:
            lo, hi = (int(getattr(cfg, 'sel_min_chars', 1)), int(getattr(cfg, 'sel_max_chars', 500)))
        except Exception:
            lo, hi = (1, 500)
        if len(s) < lo or len(s) > hi:
            return False
        else:
            if not _HAS_WORD.search(s):
                return False
            else:
                t = (translated or '').strip()
                if t and s == t:
                    return False
                else:
                    m = (mirror or '').strip()
                    if m and s == m:
                        return False
                    else:
                        return True
class SelPopup:
    """划词翻译悬浮窗：方向选框 + 原文 + 译文 + 复制/关闭。与实时镜像小窗相互独立。\n\n    v2.5.3：窗体默认 480x320（用户反馈 360x190 太小），右下角拖角可缩放，\n    尺寸写入 cfg.sel_win_w/h 下次启动保持。\n    """
    MIN_W, MIN_H = (340, 230)
    def __init__(self, root, cfg, handlers=None):
        self.cfg = cfg
        self.handlers = dict(handlers or {})
        self.visible = False
        self._src = ''
        self._out = ''
        self._w = max(self.MIN_W, int(getattr(cfg, 'sel_win_w', 480) or 480))
        self._h = max(self.MIN_H, int(getattr(cfg, 'sel_win_h', 320) or 320))
        top = tk.Toplevel(root)
        self.top = top
        top.withdraw()
        top.overrideredirect(True)
        top.geometry('%dx%d+140+140' % (self._w, self._h))
        top.configure(bg=BG)
        top.attributes('-topmost', False)
        self.f_s = tkfont.Font(family='Microsoft YaHei UI', size=9)
        self.f_b = tkfont.Font(family='Microsoft YaHei UI', size=10)
        self.f_bb = tkfont.Font(family='Microsoft YaHei UI', size=10, weight='bold')
        self.f_en = tkfont.Font(family='Segoe UI', size=10)
        head = tk.Frame(top, bg=HEAD, height=24)
        head.pack(fill='x')
        self.lbl_title = tk.Label(head, text='划词翻译', bg=HEAD, fg='white', font=self.f_bb)
        self.lbl_title.pack(side='left', padx=8)
        close = tk.Label(head, text='✕', bg=HEAD, fg='#dcdcdc', font=self.f_b, cursor='hand2')
        close.pack(side='right', padx=8)
        close.bind('<Button-1>', lambda e: self._fire('close'))
        head.bind('<B1-Motion>', self._drag)
        self._dir_src = getattr(cfg, 'sel_source_lang', '') or '中文'
        self._dir_tgt = getattr(cfg, 'sel_target_lang', '') or '英文'
        _langs = [str(x) for x in getattr(cfg, 'languages', None) or []]
        self._tgt_langs = _langs or ['英文', '日文', '韩文']
        self._src_langs = source_language_options(_langs)
        self._picker = None
        self._picker_rows = []
        self._rs = None
        drow = tk.Frame(top, bg=BG)
        drow.pack(fill='x', padx=8, pady=(4, 0))
        self.src_btn = self._pick_btn(drow, self._dir_src, lambda: self.open_picker('src'))
        self.src_btn.pack(side='left')
        tk.Label(drow, text='→', bg=BG, fg=MUTED, font=self.f_s).pack(side='left', padx=4)
        self.tgt_btn = self._pick_btn(drow, self._dir_tgt, lambda: self.open_picker('tgt'))
        self.tgt_btn.pack(side='left')
        body = tk.Frame(top, bg=BG)
        body.pack(fill='both', expand=True, padx=8, pady=(5, 2))
        tk.Label(body, text='选中原文', bg=BG, fg=MUTED, font=self.f_s, justify='left').pack(anchor='w')
        self.src = tk.Label(body, text='', bg=FIELD, fg=TXT, font=self.f_b, justify='left', wraplength=330, anchor='nw', padx=4, pady=2)
        self.src.pack(fill='x', pady=(1, 4))
        self.lbl_lang = tk.Label(body, text='译文', bg=BG, fg=MUTED, font=self.f_s, justify='left')
        self.lbl_lang.pack(anchor='w')
        self.res = tk.Text(body, height=3, wrap='word', bg='#233043', fg='#dceaff', relief='flat', bd=0, font=self.f_en, selectbackground='#4a6fd8', state='disabled')
        self.res.pack(fill='both', expand=True, pady=(1, 0))
        foot = tk.Frame(top, bg=BG)
        foot.pack(fill='x', padx=8, pady=(2, 6))
        self._btn(foot, '复制译文', GREEN, lambda: self._fire('copy'), side='left')
        self._btn(foot, '关闭', GRAY, lambda: self._fire('close'), side='left')
        self.lbl_status = tk.Label(foot, text='', bg=BG, fg=MUTED, font=self.f_s)
        self.lbl_status.pack(side='right')
        self.grip = tk.Label(top, text='◢', bg=BG, fg=MUTED, font=self.f_s, cursor='size_nw_se')
        self.grip.place(relx=1.0, rely=1.0, anchor='se')
        self.grip.bind('<ButtonPress-1>', self._rs_start)
        self.grip.bind('<B1-Motion>', self._rs_motion)
        self.grip.bind('<ButtonRelease-1>', self._rs_done)
        top.bind('<Configure>', self._on_configure)
        try:
            top.update_idletasks()
        except Exception:
            pass
        self._apply_exstyle()
        top.after(50, self._apply_exstyle)
    def _btn(self, parent, text, color, cmd, side='right'):
        tk.Button(parent, text=text, bg=color, fg='white', relief='flat', bd=0, padx=8, pady=2, font=self.f_s, cursor='hand2', activebackground='#3f83f8', activeforeground='white', command=cmd).pack(side=side, padx=(0, 4))
    def _pick_btn(self, parent, name, cmd):
        """方向行里的语言选框：普通 tk.Button（NOACTIVATE 窗里唯一验证过能用的形态）。"""
        return tk.Button(parent, text='%s ▾' % name, relief='flat', bd=0, bg=FIELD, fg=TXT, activebackground=BLUE, activeforeground='white', font=self.f_s, cursor='hand2', padx=6, highlightthickness=0, command=cmd)
    def _fire(self, k):
        fn = self.handlers.get(k)
        if fn:
            fn()
    def _drag(self, ev):
        self.top.geometry(f'+{ev.x_root - 60}+{ev.y_root - 12}')
    def _rs_start(self, ev):
        self._rs = (ev.x_root, ev.y_root, self._w, self._h)
    def _rs_motion(self, ev):
        if not self._rs:
            return
        else:
            x0, y0, w0, h0 = self._rs
            sw, sh = (self.top.winfo_screenwidth(), self.top.winfo_screenheight())
            w = max(self.MIN_W, min(w0 + ev.x_root - x0, sw - 20))
            h = max(self.MIN_H, min(h0 + ev.y_root - y0, sh - 20))
            if (w, h) != (self._w, self._h):
                self._w, self._h = (w, h)
                self.top.geometry('%dx%d' % (w, h))
    def _rs_done(self, _ev):
        self._rs = None
        self._fire('resize')
    def current_size(self):
        return (self._w, self._h)
    def _on_configure(self, ev):
        """窗体变宽/变高时，原文标签的换行宽度跟着重算，否则放大后右侧留白。"""
        try:
            if ev.widget is self.top and int(ev.width) > 1:
                self.src.configure(wraplength=max(120, int(ev.width) - 34))
        except Exception:
            pass
    def _apply_exstyle(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id()) or self.top.winfo_id()
            s = ctypes.windll.user32.GetWindowLongW(hwnd, (-20))
            ctypes.windll.user32.SetWindowLongW(hwnd, (-20), s & (-129) | 262144 | 134217728)
        except Exception:
            self.top.after(150, self._apply_exstyle)
    def _picker_alive(self) -> bool:
        if self._picker is None:
            return False
        else:
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
    def open_picker(self, side: str):
        """点选框弹/收对应侧的语言列表。点一行 = 按互换规则更新方向并收起。"""
        if self._picker_alive():
            self._close_picker()
            return
        else:
            cur = self._dir_src if side == 'src' else self._dir_tgt
            names = self._src_langs if side == 'src' else self._tgt_langs
            win = tk.Toplevel(self.top)
            self._picker = win
            win.overrideredirect(True)
            win.configure(bg=FIELD)
            win.attributes('-topmost', True)
            head = tk.Frame(win, bg=HEAD)
            head.pack(fill='x')
            tk.Label(head, text='选择源语言' if side == 'src' else '选择目标语言', bg=HEAD, fg='white', font=self.f_s).pack(side='left', padx=6, pady=1)
            x_btn = tk.Label(head, text='✕', bg=HEAD, fg='#dcdcdc', font=self.f_s, cursor='hand2')
            x_btn.pack(side='right', padx=6)
            x_btn.bind('<Button-1>', lambda e: self._close_picker())
            self._picker_rows = []
            for name in names:
                cmd = lambda n=name: (self.select_pick(side, n), self._close_picker())
                lbl = tk.Label(win, text=('✓ ' if name == cur else '   ') + name, bg=FIELD, fg=TXT, font=self.f_s, anchor='w', padx=8, pady=2, cursor='hand2')
                lbl.pack(fill='x')
                lbl.bind('<Button-1>', lambda e, c=cmd: c())
                lbl.bind('<Enter>', lambda e, w=lbl: w.configure(bg='#4a6fd8'))
                lbl.bind('<Leave>', lambda e, w=lbl: w.configure(bg=FIELD))
                self._picker_rows.append((lbl, name, cmd))
            if not self._picker_rows:
                tk.Label(win, text='（语言列表为空，去设置窗口添加）', bg=FIELD, fg=MUTED, font=self.f_s, padx=8, pady=4).pack(anchor='w')
            btn = self.src_btn if side == 'src' else self.tgt_btn
            win.update_idletasks()
            bw, bh = (win.winfo_reqwidth(), win.winfo_reqheight())
            bx, by = (btn.winfo_rootx(), btn.winfo_rooty())
            sw, sh = (win.winfo_screenwidth(), win.winfo_screenheight())
            w = max(bw, 110)
            x = max(0, min(bx, sw - w - 4))
            y = by + btn.winfo_height() + 2
            if y + bh > sh - 4:
                y = max(0, by - bh - 2)
            win.geometry('%dx%d+%d+%d' % (w, bh, x, y))
            def _style():
                try:
                    hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
                    s = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, s | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
                except Exception:
                    win.after(120, _style)
            try:
                win.update_idletasks()
            except Exception:
                pass
            _style()
            win.after(60, _style)
    def select_pick(self, side: str, name: str):
        """列表点选：应用互换规则 → 刷新两个按钮 → 触发 dir 回调（由主程序落盘+重译）。"""
        self._dir_src, self._dir_tgt = apply_direction_pick(self._dir_src, self._dir_tgt, side, name)
        self._sync_dir()
        self._fire('dir')
    def direction(self):
        return (self._dir_src, self._dir_tgt)
    def set_direction(self, src: str, tgt: str):
        """外部（镜像小窗换目标语言、设置保存）同步显示，不触发回调（防回环）。"""
        if src:
            self._dir_src = src
        if tgt:
            self._dir_tgt = tgt
        self._sync_dir()
    def set_language_lists(self, langs):
        """设置窗口保存后重灌两侧列表；当前方向若已不在列表里，拉回合法值。"""
        langs = [str(x).strip() for x in langs or [] if str(x).strip()]
        if langs:
            self._tgt_langs = list(langs)
            self._src_langs = source_language_options(langs)
        if self._dir_src not in self._src_langs:
            self._dir_src = '中文' if '中文' in self._src_langs else self._src_langs[0]
        if self._dir_tgt not in self._tgt_langs:
            self._dir_tgt = self._tgt_langs[0] if self._tgt_langs else '英文'
        self._close_picker()
        self._sync_dir()
    def _sync_dir(self):
        try:
            self.src_btn.configure(text='%s ▾' % self._dir_src)
            self.tgt_btn.configure(text='%s ▾' % self._dir_tgt)
            self.lbl_lang.configure(text='译文 → %s（源：%s）' % (self._dir_tgt, self._dir_src))
        except Exception:
            return None
    def current_source(self) -> str:
        return self._src
    def show(self, x=None, y=None, w=None, h=None):

        if not self.visible:
            self.top.deiconify()
            self.visible = True
        self._apply_exstyle()
        w = w or self._w
        h = h or self._h
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        w = max(self.MIN_W, min(int(w), sw - 20))
        h = max(self.MIN_H, min(int(h), sh - 120))
        self._w, self._h = (w, h)
        if x is None:
            x = self.top.winfo_x()
        if y is None:
            y = self.top.winfo_y()
        x = max(0, min(int(x), sw - w - 6))
        y = max(0, min(int(y), sh - h - 60))
        self.top.geometry(f'{w}x{h}+{x}+{y}')
        self.top.attributes('-topmost', False)
        self.top.lift()
        u = ctypes.windll.user32
        def hwnd():
            return u.GetParent(self.top.winfo_id()) or self.top.winfo_id()
        try:
            self._fg0 = u.GetForegroundWindow()
        except Exception:
            self._fg0 = None
        try:
            self.top.after_cancel(self._fg_after)
        except Exception:
            pass
        def watch():
            if not self.visible:
                return
            try:
                fg = u.GetForegroundWindow()
                allowed = {hwnd(), self._fg0}
                picker = getattr(self, '_picker', None)
                if picker is not None:
                    try:
                        allowed.add(u.GetParent(picker.winfo_id()) or picker.winfo_id())
                    except Exception:
                        pass
                if fg and fg not in allowed:
                    self.visible = False
                    u.ShowWindow(hwnd(), 6)
                    return
            except Exception:
                pass
            self._fg_after = self.top.after(200, watch)
        def on_map(_ev):
            try:
                if self.top.state() != 'iconic':
                    self.visible = True
                    self._fg0 = u.GetForegroundWindow()
                    try:
                        self.top.after_cancel(self._fg_after)
                    except Exception:
                        pass
                    self._fg_after = self.top.after(200, watch)
            except Exception:
                return
        self.top.bind('<Map>', on_map)
        self._fg_after = self.top.after(200, watch)
    def hide(self):
        self._close_picker()
        if self.visible:
            self.top.withdraw()
            self.visible = False
    def set_source(self, text: str):
        self._src = text or ''
        shown = self._src if len(self._src) <= 400 else self._src[:400] + ' …'
        self.src.configure(text=shown)
    def set_result(self, text: str):
        self._out = text or ''
        self.res.configure(state='normal')
        self.res.delete('1.0', 'end')
        self.res.insert('1.0', self._out)
        self.res.configure(state='disabled')
    def current_result(self) -> str:
        return self._out
    def set_status(self, msg, color=MUTED):
        try:
            self.lbl_status.configure(text=msg, fg=color)
        except Exception:
            return None
    def set_lang(self, lang: str):
        """兼容旧调用：只更新目标语言显示（方向以 set_direction/direction 为准）。"""
        if lang:
            self.set_direction(None, lang)
    def exstyle(self) -> int:
        try:
            hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id()) or self.top.winfo_id()
            return int(ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
        except Exception:
            return 0