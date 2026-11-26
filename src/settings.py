# -*- coding: utf-8 -*-
"""设置窗口：把 config.json 里的每一项做成可视表单。

v2.2 的"配置"是托盘菜单里「打开配置文件」→ os.startfile(config.json) →
用户拿记事本改 json。三个后果：改错一个引号配置就废、云端 API Key 没地方填、
热键被占用看不见。这一版把配置做成窗口：

- 分组表单（翻译服务 / 热键 / 翻译行为 / 小窗与监听 / 兼容与集成）
- 热键**点进框里直接按组合键**录入，旁边有「检测」按钮当场告诉你这个键能不能用
- 云端服务有 API Key 输入框（带掩码 + 显示开关）+「测试连接」「列出模型」
- 「保存」写盘并**即时生效**（热键重注册、监听参数、唤醒开关、抓取程序名单）
- 「恢复默认」把表单回到出厂值（不落盘，要用户再点保存）

界面代码与主循环分离：build_settings_window() 只建窗、返回 Toplevel，
面板对象挂在 win.panel 上，字段变量在 win.panel.vars 里，可被自动化测试直接读。
"""
import ctypes
import threading
import tkinter as tk
from tkinter import ttk

import hotkeys
from config import Config, config_dir, config_path, log_path

BG, CARD, TXT, MUTED = '#f4f5f7', '#ffffff', '#1c1d1f', '#6b7280'
ACCENT, GREEN, RED, FIELD = '#2b5cd6', '#1f9d55', '#c5221f', '#fbfbfc'

FONT = 'Microsoft YaHei UI'

SECTIONS = [
    ('① 翻译服务（本地 LM Studio 或任意 OpenAI 兼容云端）', [
        ('api_base', '服务地址', 'combo_edit'),
        ('model', '模型名（留空 = 自动探测）', 'combo_edit'),
        ('api_key', 'API Key（云端必填，本地留空）', 'secret'),
        ('model_hint', '自动探测优先词（逗号分隔）', 'str'),
        ('request_timeout', '请求超时（秒）', 'int'),
        ('max_tokens', '最大输出 token', 'int'),
        ('temperature', '温度（0 最稳）', 'float'),
    ]),
    ('② 全局热键（点进框里直接按下组合键即可录入）', [
        ('hotkey_translate', '翻译 / 抓取', 'key'),
        ('hotkey_toggle', '显示·隐藏小窗', 'key'),
        ('hotkey_replace', '替换输入框', 'key'),
        ('hotkey_undo', '撤销替换', 'key'),
        ('hotkey_selection', '划词翻译（微信/QQ）', 'key'),
        ('hotkey_extra_fallbacks', '翻译键的备用键（分号分隔）', 'str'),
    ]),
    ('③ 翻译行为', [
        ('source_lang', '镜像源语言（实时小窗）', 'str'),
        ('target_lang', '镜像目标语言', 'str'),
        ('sel_source_lang', '划词源语言', 'str'),
        ('sel_target_lang', '划词目标语言', 'str'),
        ('sel_link_langs', '划词与镜像语言联动（勾选=耦合，留空=各自独立）', 'bool'),
        ('languages', '可选目标语言（逗号分隔）', 'str'),
        ('max_chars', '小窗字数上限', 'int'),
        ('chunk_size', '长文分段每块字数', 'int'),
        ('auto_retranslate', '选语言后自动重译', 'bool'),
        ('retranslate_min_chars', '自动重译最少字数', 'int'),
        ('prompt_template', '提示词模板（可用 {source} {target} {source_text}）', 'text'),
        ('nllb_base', 'NLLB 小语种服务地址（留空=禁用旁路）', 'str'),
        ('nllb_langs', 'NLLB 路由语言（逗号分隔）', 'str'),
        ('nllb_polish', '小语种→中文自动润色（NLLB 初译 + 主模型译后编辑；关闭=NLLB 直出）', 'bool'),
    ]),
    ('④ 小窗与监听', [
        ('auto_show', '点到输入框自动弹出小窗', 'bool'),
        ('sel_watch', '划词自动翻译（网页/QQNT/Word 等）', 'bool'),
        ('sel_poll_ms', '选区轮询间隔（毫秒）', 'int'),
        ('sel_max_chars', '划词自动翻译字数上限', 'int'),
        ('follow_caret', '跟随光标逐字刷新', 'bool'),
        ('topmost', '小窗总在最前', 'bool'),
        ('idle_ms', '静止多久浮出操作条（毫秒）', 'int'),
        ('poll_fast_ms', '打字时轮询间隔（毫秒）', 'int'),
        ('poll_slow_ms', '静止时轮询间隔（毫秒）', 'int'),
        ('caret_follow_px', '光标位移阈值（像素）', 'int'),
        ('popup_width', '小窗宽（像素）', 'int'),
        ('popup_height', '小窗高（像素）', 'int'),
        ('mirror_password', '镜像密码框（默认不镜像）', 'bool'),
    ]),
    ('⑤ 兼容与集成', [
        ('kick_accessibility', '自动唤醒网页无障碍（Cherry Studio 等必需）', 'bool'),
        ('blind_apps', '只能抓取的程序（逗号分隔，微信已在列）', 'str'),
        ('blind_auto_grab', '在抓取型程序里按翻译键 = 抓取并翻译', 'bool'),
        ('word_use_com', 'Word/WPS 走 COM 精细替换', 'bool'),
        ('history_size', '替换历史条数', 'int'),
        ('autostart', '开机自启', 'bool'),
        ('log_level', '日志级别', 'combo'),
    ]),
]

INT_RANGE = {
    'request_timeout': (5, 600), 'max_tokens': (64, 32000),
    'max_chars': (20, 5000), 'chunk_size': (40, 1000),
    'retranslate_min_chars': (1, 50), 'idle_ms': (200, 10000),
    'poll_fast_ms': (20, 2000), 'poll_slow_ms': (50, 5000),
    'caret_follow_px': (0, 200), 'popup_width': (240, 1400),
    'popup_height': (160, 1000), 'history_size': (1, 100),
    'sel_poll_ms': (100, 3000), 'sel_max_chars': (5, 2000),
}
LIST_FIELDS = {'languages', 'nllb_langs', 'blind_apps'}
KEY_FIELD_BY_HID = {'hotkey_translate': 1, 'hotkey_toggle': 2,
                    'hotkey_replace': 3, 'hotkey_undo': 4,
                    'hotkey_selection': 5}
KEY_FIELD_BY_HID_REV = {v: k for k, v in KEY_FIELD_BY_HID.items()}
_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
_KEYSYM_FIX = {'return': 'enter', 'escape': 'esc', 'prior': 'pgup',
               'next': 'pgdn', 'delete': 'del', 'insert': 'ins', 'kapital': 'capslock'}
_IGNORED_KEYSYMS = {'num_lock', 'shift', 'control', 'alt_l', 'shift_r', 'control_l',
                    'caps_lock', 'tab', 'control_r', 'meta_r', 'super_l', 'meta_l',
                    'alt_r', 'alt', 'scroll_lock', 'super_r', 'shift_l'}


def _vk_down(vk: int) -> bool:
    return bool(ctypes.windll.user32.GetKeyState(vk) & 32768)


class SettingsPanel:
    """表单本体。所有字段变量在 self.vars[key]，测试直接读。"""

    def __init__(self, top, cfg, hooks=None):
        self.top = top
        self.cfg = cfg
        self.hooks = dict(hooks or {})
        self.vars = {}
        self.key_vars = {}
        self.key_status = {}
        self._key_capture = {}
        self._show_key = False
        self._busy = False
        self.last_error = ''

    def build(self):
        self._body()
        self._footer()
        self._load_from_config()
        return self.top

    def _body(self):
        wrap = tk.Frame(self.top, bg=BG)
        wrap.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(wrap, orient='vertical', command=self.canvas.yview)
        self.form = tk.Frame(self.canvas, bg=BG)
        self.form_id = self.canvas.create_window((0, 0), window=self.form, anchor='nw')
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.form.bind('<Configure>',
                       lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.form.bind('<MouseWheel>', self._wheel)
        for title, fields in SECTIONS:
            card = tk.Frame(self.form, bg=CARD, bd=1, relief='solid')
            card.pack(fill='x', padx=12, pady=(10, 0))
            tk.Label(card, text=title, bg=CARD, fg=ACCENT, font=(FONT, 10, 'bold'),
                     anchor='w', justify='left').pack(fill='x', padx=10, pady=(8, 4))
            for key, label, kind in fields:
                self._row(card, key, label, kind)
            if title.startswith('①'):
                self._service_buttons(card)
            if title.startswith('②'):
                self._hotkey_note(card)

    def _wheel(self, ev):
        self.canvas.yview_scroll(int(-ev.delta / 120), 'units')

    def _row(self, card, key, label, kind):
        row = tk.Frame(card, bg=CARD)
        row.pack(fill='x', padx=10, pady=2)
        tk.Label(row, text=label, bg=CARD, fg=TXT, font=(FONT, 9), anchor='w',
                 width=34, justify='left').pack(side='left')
        if kind == 'bool':
            v = tk.BooleanVar()
            self.vars[key] = v
            tk.Checkbutton(row, text='', variable=v, bg=CARD, activebackground=CARD,
                           font=(FONT, 9)).pack(side='left')
            return
        if kind == 'combo':
            v = tk.StringVar()
            self.vars[key] = v
            vals = _LOG_LEVELS if key == 'log_level' else []
            ttk.Combobox(row, textvariable=v, values=vals, width=42,
                         state='readonly').pack(side='left', fill='x', expand=True)
            return
        if kind in ('str', 'int', 'float'):
            v = tk.StringVar()
            self.vars[key] = v
            tk.Entry(row, textvariable=v, bg=FIELD, fg=TXT, relief='solid', bd=1,
                     font=(FONT, 9)).pack(side='left', fill='x', expand=True)
            return
        if kind == 'combo_edit':
            v = tk.StringVar()
            self.vars[key] = v
            vals = list(getattr(self.cfg, 'api_presets', []) or []) if key == 'api_base' else []
            c = ttk.Combobox(row, textvariable=v, values=vals, width=44)
            c.pack(side='left', fill='x', expand=True)
            self.vars[key + '__combo'] = c
            return
        if kind == 'secret':
            v = tk.StringVar()
            self.vars[key] = v
            box = tk.Frame(row, bg=CARD)
            box.pack(side='left', fill='x', expand=True)
            e = tk.Entry(box, textvariable=v, bg=FIELD, fg=TXT, relief='solid', bd=1,
                         show='•', font=(FONT, 9))
            e.pack(side='left', fill='x', expand=True)
            self._show_var = tk.BooleanVar(value=False)
            tk.Checkbutton(box, text='显示', variable=self._show_var, bg=CARD,
                           activebackground=CARD, font=(FONT, 8),
                           command=self._toggle_key).pack(side='left', padx=4)
            self.vars[key + '__entry'] = e
            return
        if kind == 'key':
            v = tk.StringVar()
            self.vars[key] = v
            self.key_vars[KEY_FIELD_BY_HID[key]] = v
            box = tk.Frame(row, bg=CARD)
            box.pack(side='left', fill='x', expand=True)
            e = tk.Entry(box, textvariable=v, bg=FIELD, fg=TXT, relief='solid', bd=1,
                         font=(FONT, 9))
            e.pack(side='left', fill='x', expand=True)
            e.bind('<KeyPress>', lambda ev, k=key: self._capture(ev, k), add='+')
            self._key_capture[key] = e
            lbl = tk.Label(box, text='', bg=CARD, fg=MUTED, font=(FONT, 8), width=22,
                           anchor='w')
            lbl.pack(side='left', padx=4)
            self.key_status[KEY_FIELD_BY_HID[key]] = lbl
            tk.Button(box, text='检测', font=(FONT, 8), padx=6, relief='flat',
                      command=lambda k=key: self.check_hotkey(k)).pack(side='right')
            return
        if kind == 'text':
            v = tk.StringVar()
            self.vars[key] = v
            t = tk.Text(row, height=4, bg=FIELD, fg=TXT, relief='solid', bd=1,
                        font=(FONT, 9), wrap='word')
            t.pack(side='left', fill='x', expand=True)
            self.vars[key + '__text'] = t
            return

    def _service_buttons(self, card):
        box = tk.Frame(card, bg=CARD)
        box.pack(fill='x', padx=10, pady=(4, 8))
        tk.Button(box, text='测试连接', font=(FONT, 9), bg=ACCENT, fg='white', relief='flat',
                  padx=10, command=self.test_connection).pack(side='left')
        tk.Button(box, text='列出模型', font=(FONT, 9), relief='flat', padx=10,
                  command=self.list_models).pack(side='left', padx=6)
        self.svc_status = tk.Label(box, text='未测试', bg=CARD, fg=MUTED, font=(FONT, 9),
                                   anchor='w')
        self.svc_status.pack(side='left', fill='x', expand=True)

    def _hotkey_note(self, card):
        self.hotkey_note = tk.Label(card, text='', bg=CARD, fg=MUTED, font=(FONT, 8),
                                    anchor='w', justify='left', wraplength=560)
        self.hotkey_note.pack(fill='x', padx=10, pady=(2, 8))
        self.refresh_hotkey_status()

    def _footer(self):
        foot = tk.Frame(self.top, bg=BG)
        foot.pack(fill='x', side='bottom')
        self.status = tk.Label(foot, text='', bg=BG, fg=MUTED, font=(FONT, 9),
                               anchor='w', justify='left')
        self.status.pack(side='left', fill='x', expand=True, padx=10, pady=6)
        tk.Button(foot, text='打开日志', font=(FONT, 8), relief='flat', padx=6,
                  command=self.open_log).pack(side='right', padx=4, pady=4)
        tk.Button(foot, text='打开 config.json', font=(FONT, 8), relief='flat', padx=6,
                  command=self.open_json).pack(side='right', padx=4, pady=4)
        tk.Button(foot, text='恢复默认', font=(FONT, 8), relief='flat', padx=6,
                  command=self.reset_defaults).pack(side='right', padx=4, pady=4)
        tk.Button(foot, text='关闭', font=(FONT, 8), relief='flat', padx=6,
                  command=self.close).pack(side='right', padx=4, pady=4)
        tk.Button(foot, text='保存并生效', font=(FONT, 10, 'bold'), bg=GREEN, fg='white',
                  relief='flat', padx=12, command=self.save).pack(side='right', padx=6, pady=4)

    def _load_from_config(self):
        d = self.cfg.__dict__
        for key, _label, kind in [f for _t, fs in SECTIONS for f in fs]:
            val = d.get(key, '')
            if key in LIST_FIELDS:
                val = ', '.join(list(val or []))
            self.set_field(key, val)
        self.set_field('api_key', self.cfg.api_key or '')

    def set_field(self, key, value):
        v = self.vars.get(key)
        if v is None:
            return
        v.set('' if value is None else str(value))
        t = self.vars.get(key + '__text')
        if t is not None:
            t.delete('1.0', 'end')
            t.insert('1.0', str(value or ''))

    def get_values(self) -> dict:
        out = {}
        for _t, fs in SECTIONS:
            for key, _label, kind in fs:
                if key in LIST_FIELDS:
                    out[key] = [x.strip() for x in str(self.vars[key].get()).split(',') if x.strip()]
                elif kind == 'text':
                    t = self.vars.get(key + '__text')
                    out[key] = t.get('1.0', 'end').strip() if t is not None else ''
                else:
                    out[key] = self.vars[key].get()
        return out

    def _capture(self, ev, key):
        ks = str(ev.keysym or '').lower()
        if ks in _IGNORED_KEYSYMS:
            return 'break'
        key_name = _KEYSYM_FIX.get(ks, ks)
        if not key_name:
            return 'break'
        mods = []
        if _vk_down(17):
            mods.append('ctrl')
        if _vk_down(24):
            mods.append('alt')
        if _vk_down(16):
            mods.append('shift')
        if _vk_down(91) or _vk_down(92):
            mods.append('win')
        if not mods:
            self._key_status_line(key, '必须带修饰键', RED)
            return 'break'
        spec = hotkeys.normalize('+'.join(mods + [key_name]))
        self.vars[key].set(spec)
        self._key_status_line(key, '已录入，保存后生效', ACCENT)
        return 'break'

    def _key_status_line(self, key, msg, color):
        hid = KEY_FIELD_BY_HID.get(key)
        lbl = self.key_status.get(hid)
        if lbl is not None:
            try:
                lbl.configure(text=msg, fg=color)
            except Exception:
                pass

    def check_hotkey(self, key):
        spec = self.vars[key].get()
        hid = KEY_FIELD_BY_HID.get(key)
        st = {}
        try:
            st = (self.hooks.get('hotkey_status') or dict)() or {}
        except Exception:
            st = {}
        cur = (st.get(hid) or {}).get('effective', '')
        if spec and spec == cur:
            self._key_status_line(key, '当前生效中', GREEN)
            return True
        ok, note = hotkeys.test_spec(spec)
        self._key_status_line(key, note, GREEN if ok else RED)
        return ok

    def refresh_hotkey_status(self):
        st = {}
        try:
            st = (self.hooks.get('hotkey_status') or dict)() or {}
        except Exception:
            st = {}
        lines = []
        for hid in tuple(KEY_FIELD_BY_HID_REV):
            v = st.get(hid) or {}
            if not v:
                continue
            eff = v.get('effective', '')
            want = v.get('spec', '')
            key = KEY_FIELD_BY_HID_REV.get(hid)
            if eff and eff != want:
                lines.append(f'「{hotkeys.HOTKEY_NAMES[hid]}」{want} 被占用 → 已改用 {eff}')
            elif not eff:
                lines.append(f'「{hotkeys.HOTKEY_NAMES[hid]}」{want} 注册失败（{v.get("err") or "被占用"}）—— 请换个键')
            if key and eff:
                self.vars[key].set(want)
                self._key_status_line(key, '生效中：' + eff, GREEN)
        self.hotkey_note.configure(
            text='；'.join(lines) if lines else
            '%d 把热键全部按配置生效。' % len(tuple(KEY_FIELD_BY_HID_REV)))

    def _apply_draft_to_cfg(self) -> Config:
        vals = self.get_values()
        new = Config()
        new.__dict__.update(self.cfg.__dict__)
        for k, v in vals.items():
            if k in LIST_FIELDS:
                setattr(new, k, v)
            elif k in INT_RANGE:
                lo, hi = INT_RANGE[k]
                try:
                    n = int(float(str(v).strip()))
                except Exception:
                    raise ValueError('「%s」要填 %d~%d 之间的整数' % (k, lo, hi))
                if not lo <= n <= hi:
                    raise ValueError('「%s」要在 %d~%d 之间' % (k, lo, hi))
                setattr(new, k, n)
            elif k == 'temperature':
                try:
                    t = float(str(v).strip())
                except Exception:
                    raise ValueError('「温度」要填 0~2 之间的小数')
                if not 0.0 <= t <= 2.0:
                    raise ValueError('「温度」要在 0~2 之间')
                setattr(new, k, t)
            elif k == 'log_level':
                lv = str(v).strip().upper()
                if lv not in _LOG_LEVELS:
                    raise ValueError('「日志级别」只能是 ' + '/'.join(_LOG_LEVELS))
                setattr(new, k, lv)
            elif k == 'api_base':
                base = str(v).strip()
                if not (base.startswith('http://') or base.startswith('https://')):
                    raise ValueError('「服务地址」要以 http:// 或 https:// 开头')
                setattr(new, k, base.rstrip('/'))
            elif k == 'nllb_base':
                base = str(v).strip()
                if base:
                    if not (base.startswith('http://') or base.startswith('https://')):
                        raise ValueError('「NLLB 服务地址」要以 http:// 开头，或留空禁用')
                    base = base.rstrip('/')
                setattr(new, k, base)
            elif k == 'api_key':
                setattr(new, k, str(v).strip())
            elif KEY_FIELD_BY_HID.get(k):
                spec = hotkeys.normalize(v)
                if hotkeys.parse(spec)[0] is None:
                    raise ValueError('「%s」的热键格式无效（示例：ctrl+alt+shift+t）'
                                     % hotkeys.HOTKEY_NAMES[KEY_FIELD_BY_HID[k]])
                setattr(new, k, spec)
            elif k == 'prompt_template':
                tpl = str(v)
                if '{source_text}' not in tpl:
                    raise ValueError('提示词模板里必须包含 {source_text}')
                setattr(new, k, tpl)
            else:
                setattr(new, k, str(v).strip())
        for k in ('auto_show', 'follow_caret', 'topmost', 'auto_retranslate', 'mirror_password',
                  'kick_accessibility', 'blind_auto_grab', 'word_use_com', 'autostart', 'sel_watch',
                  'sel_link_langs', 'nllb_polish'):
            setattr(new, k, bool(vals.get(k)))
        return new

    def test_connection(self):
        fn = self.hooks.get('test_service')
        if not fn:
            self.set_status('没有可用的测试通道', RED)
            return
        self._busy = True
        self.set_status('正在连接…', ACCENT)

        def worker():
            try:
                draft = self._apply_draft_to_cfg()
            except ValueError as e:
                self.top.after(0, self.set_status, str(e), RED)
                self._busy = False
                return
            try:
                ok, info = fn(draft)
            except Exception as e:
                ok, info = False, f'{type(e).__name__}: {e}'
            self.top.after(0, self._svc_done, ok, info)

        threading.Thread(target=worker, daemon=True).start()

    def _svc_done(self, ok, info):
        self._busy = False
        if ok:
            ids = info if isinstance(info, list) else [str(info)]
            self.set_status('连接成功，可用模型 %d 个：%s'
                            % (len(ids), ', '.join(ids[:6])), GREEN)
            combo = self.vars.get('model__combo')
            if combo is not None:
                try:
                    combo.configure(values=list(ids))
                except Exception:
                    pass
        else:
            self.set_status('连接失败：%s' % info, RED)

    def list_models(self):
        self.test_connection()

    def save(self):
        try:
            new = self._apply_draft_to_cfg()
        except ValueError as e:
            self.last_error = str(e)
            self.set_status(str(e), RED)
            return False
        self.cfg.__dict__.update(new.__dict__)
        try:
            fn = self.hooks.get('saved')
            if fn:
                fn(self.cfg)
        except Exception as e:
            self.last_error = str(e)
            self.set_status('已写入配置，但生效时出错：%s' % e, RED)
            return False
        self.last_error = ''
        self.set_status('已保存并生效（热键已重新注册）', GREEN)
        self.refresh_hotkey_status()
        return True

    def reset_defaults(self):
        d = Config().__dict__
        for key, _label, kind in [f for _t, fs in SECTIONS for f in fs]:
            val = d.get(key, '')
            if key in LIST_FIELDS:
                val = ', '.join(list(val or []))
            self.set_field(key, val)
        self.set_field('api_key', '')
        self.set_status('已恢复默认值（还没落盘，点「保存并生效」才写入）', ACCENT)

    def set_status(self, msg, color=MUTED):
        try:
            self.status.configure(text=msg, fg=color)
        except Exception:
            pass

    def status_text(self) -> str:
        try:
            return self.status.cget('text')
        except Exception:
            return ''

    def _toggle_key(self):
        e = self.vars.get('api_key__entry')
        if e is not None:
            e.configure(show='' if self._show_var.get() else '•')

    def open_log(self):
        try:
            os_startfile(log_path())
        except Exception:
            self.set_status('日志文件还没生成', MUTED)

    def open_json(self):
        try:
            os_startfile(config_path())
        except Exception:
            pass

    def close(self):
        try:
            self.top.destroy()
        except Exception:
            pass


def os_startfile(path):
    import os
    os.startfile(path)


def build_settings_window(root, cfg, hooks=None) -> tk.Toplevel:
    top = tk.Toplevel(root)
    top.title('输入翻译桥 · 设置')
    top.geometry('620x620')
    top.configure(bg=BG)
    top.minsize(520, 420)
    panel = SettingsPanel(top, cfg, hooks)
    top.panel = panel
    panel.build()
    top.protocol('WM_DELETE_WINDOW', panel.close)
    top.after(60, lambda: (top.lift(), top.focus_force()))
    return top
