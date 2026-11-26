# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'hotkeys.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""全局热键：注册 + **占用检测** + 空闲键降级 + 运行期重注册 + 状态上报\n\nv2.2 的写法是：\n    if user32.RegisterHotKey(None, hid, mods, vk):\n        self._ids.append(hid)\n失败就静默跳过。本机 2026-10-10 实测：ctrl+alt+t / ctrl+alt+b / ctrl+alt+y /\nctrl+alt+z **四个组合全部注册失败**（全被机器上其它程序占了，截图工具占了 T）。\n于是程序一个热键都没挂上，用户按 Ctrl+Alt+T 触发的是那个截图工具 ——\n弹出截屏选择框，程序这边什么都没发生。这就是\"微信里热键抓不到内容\"的直接原因。\n\n所以这一版把规则改成：\n1. 注册结果**必须**成为可查询的状态，并通过回调上报（小窗状态条 / 托盘 / 日志）；\n2. 配置里的键被占用时，自动在备用键里挑一个空闲的挂上，并告知\"已改用 X\"；\n3. 支持运行期重注册（设置窗口里改完键，立即生效，不用重启程序）；\n4. 提供 test_spec() 给设置窗口做\"这个键现在能不能用\"的即时检测。\n"""
import ctypes
import threading
from ctypes import wintypes
user32 = ctypes.windll.user32
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = (1, 2, 4, 8)
MOD_NOREPEAT = 16384
WM_HOTKEY = 786
WM_APP = 32768
WM_RELOAD = WM_APP + 1
WM_SHUTDOWN = WM_APP + 2
HWND_MESSAGE = (-3)
HOTKEY_NAMES = {1: '翻译 / 抓取', 2: '显示·隐藏小窗', 3: '替换输入框', 4: '撤销替换', 5: '划词翻译'}
FALLBACKS = {1: ['ctrl+alt+shift+t', 'ctrl+alt+f9', 'ctrl+alt+j', 'ctrl+alt+m'], 2: ['ctrl+alt+shift+b', 'ctrl+alt+f10', 'ctrl+alt+k'], 3: ['ctrl+alt+shift+y', 'ctrl+alt+f11', 'ctrl+alt+h'], 4: ['ctrl+alt+shift+z', 'ctrl+alt+f12', 'ctrl+alt+g'], 5: ['ctrl+alt+shift+d', 'ctrl+alt+shift+u', 'ctrl+alt+shift+w']}
_MOD_NAMES = {'ctrl': MOD_CONTROL, 'control': MOD_CONTROL, 'ctl': MOD_CONTROL, 'alt': MOD_ALT, 'option': MOD_ALT, 'shift': MOD_SHIFT, 'win': MOD_WIN, 'windows': MOD_WIN, 'super': MOD_WIN, 'cmd': MOD_WIN, 'meta': MOD_WIN}
_NAMED_KEYS = {'space': 32, 'enter': 13, 'return': 13, 'tab': 9, 'esc': 27, 'escape': 27, 'home': 36, 'end': 35, 'pgup': 33, 'pgdn': 34, 'pageup': 33, 'pagedown': 34, 'del': 46, 'delete': 46, 'ins': 45, 'insert': 45, 'printscreen': 44, 'prtsc': 44, 'capslock': 20, 'up': 38, 'down': 40, 'left': 37, 'right': 39, 'minus': 109, 'plus': 107, 'comma': 188, 'period': 190, 'slash': 191, 'backslash': 220, 'semicolon': 186, 'quote': 222}
for _i in range(1, 25):
    _NAMED_KEYS['f%d' % _i] = 112 + _i - 1
def normalize(spec: str) -> str:
    """把 \'Ctrl + Alt + T\'、\'alt+ctrl+t\' 统一成 \'ctrl+alt+t\'（修饰键按固定顺序）。"""
    parts = [p.strip().lower() for p in str(spec or '').split('+') if p.strip()]
    mods, key = ([], None)
    for p in parts:
        if p in _MOD_NAMES:
            if p not in mods:
                mods.append(p)
        else:
            key = p
    order = ['ctrl', 'alt', 'shift', 'win']
    mods = [m for m in order if m in mods]
    if key:
        mods.append(key)
    return '+'.join(mods)
def parse(spec: str):
    """\'ctrl+alt+shift+t\' → (mods, vk)；无效返回 (None, None)。\n\n    必须带修饰键：全局热键不带修饰键会把用户的正常打字吞掉，\n    这种组合直接判无效，不注册。\n    """
    parts = [p.strip().lower() for p in str(spec or '').split('+') if p.strip()]
    if not parts:
        return (None, None)
    else:
        key = None
        mods = 0
        for p in parts:
            if p in _MOD_NAMES:
                mods |= _MOD_NAMES[p]
            else:
                key = p
        if not key:
            return (None, None)
        else:
            vk = None
            if len(key) == 1:
                if key.isalnum():
                    vk = ord(key.upper())
            else:
                vk = _NAMED_KEYS.get(key)
            if not vk:
                return (None, None)
            else:
                if not mods:
                    return (None, None)
                else:
                    return (mods | MOD_NOREPEAT, vk)
_parse = parse
def test_spec(spec: str) -> tuple:
    """即时检测一个组合此刻能不能注册。返回 (可用?, 说明)。\n\n    注册成功立刻反注册，纯探测不占用。\n    注意：如果这个组合正被**本程序自己**用着，这里会返回\"被占用\" ——\n    设置窗口会拿 hotkey 状态去区分这两种情况，不会把话说错。\n    """
    mods, vk = parse(spec)
    if mods is None:
        return (False, '格式无效（示例：ctrl+alt+shift+t）')
    else:
        if user32.RegisterHotKey(None, 3855, mods, vk):
            user32.UnregisterHotKey(None, 3855)
            return (True, '可用')
        else:
            return (False, '已被其它程序占用')
class HotkeyManager:
    """热键线程：消息专用窗口 + RegisterHotKey + 可重入的 reload。"""
    def __init__(self, cfg, callback, on_status=None):
        self.callback = callback
        self.on_status = on_status
        self._lock = threading.Lock()
        self._registered = {}
        self._status = {}
        self._hwnd = None
        self._reload_cfg = None
        self._ready = threading.Event()
        self._alive = False
        threading.Thread(target=self._loop, args=(cfg,), daemon=True).start()
        self._ready.wait(5)
    def _make_msg_window(self):
        user32.CreateWindowExW.restype = wintypes.HWND
        h = user32.CreateWindowExW(0, 'Static', 'ImeBridgeHotkeyMsg', 0, 0, 0, 0, 0, ctypes.c_void_p(HWND_MESSAGE), None, None, None)
        return h
    def _unregister_all(self):
        for hid in list(self._registered):
            user32.UnregisterHotKey(self._hwnd, hid)
        self._registered = {}
    def _register_all(self, cfg):
        specs = [(1, getattr(cfg, 'hotkey_translate', '')), (2, getattr(cfg, 'hotkey_toggle', '')), (3, getattr(cfg, 'hotkey_replace', '')), (4, getattr(cfg, 'hotkey_undo', '')), (5, getattr(cfg, 'hotkey_selection', 'ctrl+alt+shift+d'))]
        extra = [s.strip() if s.strip() else s for s in str(getattr(cfg, 'hotkey_extra_fallbacks', '') or '').split(';')]
        self._unregister_all()
        status = {}
        for hid, spec in specs:
            want = normalize(spec)
            cands = [want] + [normalize(c) for c in FALLBACKS.get(hid, [])]
            if hid == 1:
                cands += [normalize(c) for c in extra]
            seen, eff, err = (set(), '', '')
            for cand in cands:
                if not cand or cand in seen:
                    continue
                else:
                    seen.add(cand)
                    mods, vk = parse(cand)
                    if mods is None:
                        err = '格式无效'
                    else:
                        if user32.RegisterHotKey(self._hwnd, hid, mods, vk):
                            self._registered[hid] = (mods, vk)
                            eff = cand
                            err = ''
                            break
                        else:
                            err = '被占用'
            status[hid] = {'spec': want, 'effective': eff, 'ok': bool(eff), 'changed': bool(eff) and eff != want, 'err': err}
        with self._lock:
            self._status = status
        self._notify()
        return status
    def _notify(self):
        if not self.on_status:
            return
        else:
            try:
                self.on_status(self.status())
            except Exception:
                return None
            return
    def _loop(self, cfg):
        self._hwnd = self._make_msg_window()
        self._alive = True
        try:
            self._register_all(cfg)
        except Exception:
            pass
        self._ready.set()
        msg = wintypes.MSG()
        while True:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res == 0 or res == (-1):
                break
            else:
                m = int(msg.message)
                if m == WM_HOTKEY:
                    hid = int(msg.wParam)
                    with self._lock:
                        hit = hid in self._registered
                    if not hit:
                        continue
                    else:
                        try:
                            self.callback(hid)
                        except Exception:
                            pass
                else:
                    if m == WM_RELOAD:
                        with self._lock:
                            c = self._reload_cfg
                        if c is not None:
                            try:
                                self._register_all(c)
                            except Exception:
                                pass
                    else:
                        if m == WM_SHUTDOWN:
                            break
        self._unregister_all()
        self._alive = False
    def status(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._status.items()}
    def effective(self, hid: int) -> str:
        with self._lock:
            v = self._status.get(hid) or {}
            return v.get('effective', '')
    def all_ok(self) -> bool:
        with self._lock:
            return bool(self._status) and all((v['ok'] for v in self._status.values()))
    def summary(self) -> str:
        """给小窗/托盘/日志用的一行话，必须把降级说清楚。\n        （v2.5：热键从 4 把变 5 把，数量不再写死。）"""
        st = self.status()
        if not st:
            return '热键：未初始化'
        else:
            hs = sorted(st)
            bad = [h for h in hs if not (st.get(h) or {}).get('ok')]
            moved = [h for h in hs if (st.get(h) or {}).get('ok') and (st.get(h) or {}).get('changed')]
            if not bad and (not moved):
                return '热键：%d 个全部生效' % len(hs)
            else:
                bits = []
                if moved:
                    bits.append('已改用空闲键 ' + '、'.join(('%s→%s' % (st[h]['spec'], st[h]['effective']) for h in moved)))
                if bad:
                    bits.append('注册失败 ' + '、'.join(('%s(%s)' % (HOTKEY_NAMES[h], st[h]['err'] or '被占用') for h in bad)))
                return '热键：' + '；'.join(bits)
    def reload(self, cfg) -> None:
        """设置窗口保存后调用：立即按新配置重注册，不用重启程序。"""
        with self._lock:
            self._reload_cfg = cfg
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_RELOAD, 0, 0)
    def shutdown(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_SHUTDOWN, 0, 0)