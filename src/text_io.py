# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'text_io.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""焦点检测 / 文本读写 / 剪贴板 / 模拟按键 / 光标坐标"""
global _a11y_enabled
global _blind_extra
import ctypes
import threading
import time
from ctypes import wintypes
import win32clipboard
import win32con
import win32gui
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
APP_PROFILES = {'chrome.exe': 'field', 'msedge.exe': 'field', 'firefox.exe': 'field', 'opera.exe': 'field', 'brave.exe': 'field', 'vivaldi.exe': 'field', 'wechat.exe': 'field', 'weixin.exe': 'field', 'qq.exe': 'field', 'dingtalk.exe': 'field', 'feishu.exe': 'field', 'lark.exe': 'field', 'telegram.exe': 'field', 'discord.exe': 'field', 'winword.exe': 'doc', 'wps.exe': 'doc', 'wordpad.exe': 'doc', 'wpspdf.exe': 'doc', 'pdfviewer.exe': 'doc', 'onenote.exe': 'doc', 'et.exe': 'field', 'wps.et.exe': 'field', 'excel.exe': 'field', 'notepad.exe': 'edit', 'notepad++.exe': 'edit', 'typora.exe': 'field', 'code.exe': 'field', 'devenv.exe': 'field', 'idea64.exe': 'field'}
CLASSIC_EDITS = {'SunAwtTextField', 'RichEdit50W', 'Scintilla', 'TRichEdit', 'Edit', 'RICHEDIT50W', 'Afx:404000:0', 'RichEdit20A', 'SunAwtTextArea', 'NotepadTextBox', 'wxWindowClassNR', 'TMemo', 'Afx:400000:0', 'Afx:4b0000:2', 'RichEditD2DPT', 'bosa_sdom', 'Afx:1400000:8', 'RichEdit20W', 'Afx:800000:0', 'TEdit', 'RichEdit', 'Afx:1000000:8'}
WEB_HOSTS = {'MozillaWindowClass', 'Chrome_WidgetWin_0', 'Chrome_RenderWidgetHostHWND', 'Chrome_WidgetWin_1', 'XULWindow', 'Chrome Legacy Window', 'MicrosoftEdgeWebview2Control', 'Qt681QWindowIcon', 'Qt5152QWindowIcon'}
NEVER_EDIT = {'_WwG', 'SysListView32', 'ToolbarWindow32', 'TaskbarButton', 'Progman', 'msctls_progress32', 'CabinetWClass', 'KwpsOox', 'Button', 'tooltips_class32', 'OpusApp', 'Static', 'WorkerW', 'Shell_TrayWnd', 'SysTreeView32'}
DOC_CLASSES = {'_WwG', 'WordPad Root Window', 'KwpsOox', 'WPSOffice', 'OpusApp'}
A11Y_REKICK_S = 25.0
OBJID_CLIENT = 4294967292
BLIND_APPS = {'weixinwindows.exe', 'weixin.exe', 'wechatapp.exe', 'wechat.exe'}
_blind_extra: set = set()
_a11y_done: dict = {}
_cache_class, _cache_edit, _cache_proc = ({}, {}, {})
TTL = 4.0
TTL_DYNAMIC = 0.5
def _cached(d: dict, key, ttl=TTL):
    now = time.time()
    hit = d.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    else:
        return None
def _store(d: dict, key, val, limit=4000):
    d[key] = (time.time(), val)
    if len(d) > limit:
        d.clear()
class GUITHREADINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT), ('flags', wintypes.UINT), ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND), ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND), ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND), ('rcCaret', wintypes.RECT)]
def get_class(hwnd) -> str:
    v = _cached(_cache_class, hwnd)
    if v is not None:
        return v
    else:
        buf = ctypes.create_unicode_buffer(257)
        user32.GetClassNameW(hwnd, buf, 256)
        _store(_cache_class, hwnd, buf.value)
        return buf.value
def get_process_name(hwnd) -> str:
    v = _cached(_cache_proc, hwnd)
    if v is not None:
        return v
    else:
        name = ''
        try:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = kernel32.OpenProcess(4096, False, pid.value)
            if h:
                size = wintypes.DWORD(260)
                buf = ctypes.create_unicode_buffer(260)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value).lower()
                kernel32.CloseHandle(h)
        except Exception:
            name = ''
        _store(_cache_proc, hwnd, name)
        return name
import os
def get_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value
WEB_CONTENT_HOSTS = ('Chrome_RenderWidgetHostHWND', 'Chrome Legacy Window', 'MicrosoftEdgeWebview2Control', 'XULWindow')
def _web_content_child(hwnd):
    """顶层窗口的网页内容子窗口（Chromium 系）。找不到返回 None。"""
    found = []
    def cb(child, acc):
        if user32.IsWindowVisible(child) and get_class(child) in WEB_CONTENT_HOSTS:
                acc.append(child)
        return True
    try:
        win32gui.EnumChildWindows(hwnd, cb, found)
    except Exception:
        return None
    return found[0] if found else None
class _GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]
IID_IAccessible = _GUID(1636251360, 15421, 4559, (ctypes.c_ubyte * 8)(129, 12, 0, 170, 0, 56, 155, 113))
def _release(ptr_val) -> None:
    """IUnknown::Release（vtable 第 3 项）。不释放会每踢一次泄漏一个 COM 引用。"""
    try:
        vtbl = ctypes.cast(ptr_val, ctypes.POINTER(ctypes.c_void_p))
        fn = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl.contents[2])
        fn(ptr_val)
    except Exception:
        return None
_a11y_enabled = True
def set_a11y_kick(on: bool) -> None:
    """允许用户关掉主动唤醒（会让 Electron 应用重新变成读不到）。"""
    global _a11y_enabled
    _a11y_enabled = bool(on)
def ensure_a11y(hwnd) -> bool:
    """唤醒 Chromium / Electron 的网页无障碍树。\n\n    返回「本次是否真的发起了唤醒」——调用方据此决定要不要等树建好再读。\n    Electron 应用（Cherry Studio 等）不会像 Chrome/Edge 那样在检测到 UIA 客户端时\n    自动开启网页无障碍，不踢就只能看到浏览器外壳，读不到任何网页控件。\n    """
    if not hwnd or (not _a11y_enabled):
        return False
    else:
        top = user32.GetAncestor(hwnd, 2) or hwnd
        now = time.time()
        last = _a11y_done.get(top)
        if last is not None and now - last < A11Y_REKICK_S:
            return False
        else:
            if len(_a11y_done) > 512:
                _a11y_done.clear()
            _a11y_done[top] = now
            try:
                oleacc = ctypes.windll.oleacc
            except Exception:
                return False
            targets = [top]
            try:
                kids = []
                win32gui.EnumChildWindows(top, lambda c, a: (a.append(c), True)[1], kids)
                targets += kids[:64]
            except Exception:
                pass
            kicked = False
            for t in targets:
                p = ctypes.c_void_p()
                try:
                    hr = oleacc.AccessibleObjectFromWindow(t, OBJID_CLIENT, ctypes.byref(IID_IAccessible), ctypes.byref(p))
                    if hr == 0 and p.value:
                            kicked = True
                            _release(p.value)
                except Exception:
                    pass
            return kicked
def set_blind_apps(names) -> None:
    """由配置注入额外的盲应用进程名（大小写不敏感，可省略 .exe）。"""
    global _blind_extra
    out = set()
    for n in names or []:
        n = str(n).strip().lower()
        if n:
            out.add(n if n.endswith('.exe') else n + '.exe')
    _blind_extra = out
def is_blind(hwnd) -> bool:
    """这个窗口是不是「零无障碍、只能靠剪贴板抓取」的自绘程序。"""
    if not hwnd:
        return False
    else:
        p = get_process_name(hwnd)
        return bool(p) and (p in BLIND_APPS or p in _blind_extra)
def _is_foreground(hwnd) -> bool:
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    else:
        root = user32.GetAncestor(hwnd, 2) or hwnd
        return fg == hwnd or fg == root or user32.GetAncestor(fg, 2) == root
def _class_is_web_host(cls: str) -> bool:
    """Chromium 系窗口类，外加 Qt 的 Qt<版本>QWindowIcon 系列。\n\n    写死版本号会漏：微信是 Qt51514QWindowIcon，而表里只有 Qt5152/Qt681。\n    """
    if cls in WEB_HOSTS:
        return True
    else:
        return cls.startswith('Qt') and 'QWindow' in cls
def get_focus_hwnd():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return
    else:
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        focus = hwnd
        if user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndFocus:
                focus = info.hwndFocus
        if not user32.IsWindowVisible(focus):
            root = user32.GetAncestor(focus, 2) or hwnd
            if user32.IsWindowVisible(root):
                focus = root
        if focus == hwnd:
            child = _web_content_child(hwnd)
            if child:
                return child
        return focus
FIELD_NAMES = ('EditControl', 'ComboBoxControl', 'SpinnerControl')
CONTAINER_NAMES = ('DocumentControl', 'GroupControl', 'PaneControl', 'ListControl', 'CustomControl')
ROOT_WEB_AREA = 'RootWebArea'
def _aria_readonly(el) -> bool:
    """AriaProperties 里带 readonly=true 的就是只读区域。\n\n    实测（Edge + Cherry Studio，判据干净可用）：\n      <input>                aria=\'expanded=false;multiline=false;…\'        无 readonly\n      contenteditable 输入框  aria=\'expanded=false;multiline=true;…\'         无 readonly\n      只读 <div>（消息列表）   aria=\'readonly=true;…\'                        ← 排除\n      RootWebArea（整页文档）  aria=\'readonly=true;hidden=true;…\'            ← 排除\n      readonly 的 <input>     aria=\'readonly=true;…\' 且 ValuePattern.IsReadOnly=True\n    """
    try:
        ap = el.AriaProperties or ''
    except Exception:
        return False
    return 'readonly=true' in str(ap).replace(' ', '').lower()
def _is_web_editable(el) -> bool:
    # irreducible cflow, using cdg fallback
    """网页里的「容器型输入框」——contenteditable 富文本编辑器。\n\n    Cherry Studio 的聊天框是 tiptap/ProseMirror，在 UIA 里既不是 EditControl\n    也没有 ValuePattern，而是 **GroupControl + 只有 TextPattern**（实测 ClassName\n    以 \'tiptap ProseMirror\' 开头，AutomationId=\'ed\' 一类，AriaRole=\'group\'，\n    aria 里 multiline=true 且没有 readonly）。\n    只认 FIELD_NAMES 的话这类输入框会被整片漏掉，小窗永远不弹。\n\n    三条排除项都是实测踩过或会踩的坑：\n      - RootWebArea：它的 ValuePattern 是**网址**、TextPattern 是**整页正文**；\n      - aria readonly=true：只读区域（消息列表、正文 div）——照它读就会镜像整段对话；\n      - 既无 TextPattern 又无可写 ValuePattern：读不出来，弹了也没用。\n    """
    try:
        if el is None:
            return False
        if str(el.AutomationId or '') == ROOT_WEB_AREA:
            return False
        if _aria_readonly(el):
            return False
        if el.ControlTypeName not in CONTAINER_NAMES:
            return False
        import uiautomation as auto
        try:
            vp = el.GetPattern(auto.PatternId.ValuePattern)
            if vp is not None:
                return not vp.IsReadOnly
        except Exception:
            pass
        try:
            return el.GetPattern(auto.PatternId.TextPattern) is not None
        except Exception:
            return False
    except Exception:
        return False
def _is_field(el) -> bool:
    # irreducible cflow, using cdg fallback
    """这个 UIA 元素是不是「光标能在里面、且能读能写的输入控件」。"""
    try:
        if el is None:
            return False
        if _aria_readonly(el):
            return False
        if el.ControlTypeName in FIELD_NAMES:
            return True
        return _is_web_editable(el)
    except Exception:
        return False
def _has_focus_flag(el) -> bool:
    for attr in ['HasKeyboardFocus', 'IsKeyboardFocusElement']:
        v = getattr(el, attr, None)
        if v is not None:
            return bool(v)
    return False
def _focused_field_in(root, max_depth=24, max_nodes=900):
    # irreducible cflow, using cdg fallback
    """在焦点元素的子树里找真正带键盘焦点的输入控件。\n\n    Chromium/Edge 的焦点元素经常停在最外层的 DocumentControl（RootWebArea）上，\n    它的 ValuePattern 返回的是**网址**、TextPattern 返回的是**整页文字**。\n    照它读，镜像出来的就是网址或整页正文，而不是光标所在输入框的内容。\n\n    深度 24 / 900 节点是实测定的：Cherry Studio 的聊天框在 UIA 树里位于第 29 层\n    （顶层窗口算起），从 RootWebArea 往下还有约 20 层；原来的 5 层 / 200 节点\n    连零头都够不着，搜索必然失败。\n    """
    if root is None:
        return
    stack = [(root, 0)]
    n = 0
    while stack and n < max_nodes:
        node, d = stack.pop()
        n += 1
        if d > max_depth:
            continue
        try:
            kids = node.GetChildren()
        except Exception:
            continue
        for ch in kids:
            try:
                if _is_field(ch) and _has_focus_flag(ch):
                    return ch
            except Exception:
                pass
            stack.append((ch, d + 1))
    return None
def _worth_walking(el) -> bool:
    # irreducible cflow, using cdg fallback
    """只有当焦点被报在「文档根」上时，往子树里钻才有意义。\n\n    焦点落在只读区域（实测 Cherry Studio 的消息列表：GroupControl + aria\n    readonly=true）时根本不存在被藏起来的输入框，钻一遍纯属白烧 CPU。\n    """
    try:
        if str(el.AutomationId or '') == ROOT_WEB_AREA:
            return True
        return el.ControlTypeName == 'DocumentControl'
    except Exception:
        return False
_walk_cache: dict = {}
def _focused_field_cached(hwnd, el):
    """子树搜索加 1 秒缓存。\n\n    搜一次要跨进程遍历几百个 UIA 节点，而轮询间隔只有 60~250ms；\n    用户没把光标放在输入框里时这个搜索必然失败，不缓存就会持续空转。\n    """
    now = time.time()
    hit = _walk_cache.get(hwnd)
    if hit is not None and now - hit[0] < 1.0:
        return hit[1]
    else:
        found = _focused_field_in(el)
        if len(_walk_cache) > 256:
            _walk_cache.clear()
        _walk_cache[hwnd] = (now, found)
        return found
def _kick_and_settle(hwnd) -> None:
    """需要读 UIA 之前先确保无障碍树是开的。"""
    if ensure_a11y(hwnd):
        time.sleep(0.45)
def _uia_is_editable(hwnd) -> bool:
    # irreducible cflow, using cdg fallback
    try:
        import uiautomation as auto
        _kick_and_settle(hwnd)
        el = auto.ControlFromHandle(hwnd)
        if el is None:
            el = _focused()
            if el is None or not _same_app(el, hwnd):
                return False
        if _is_field(el):
            return True
        if _worth_walking(el):
            return _focused_field_cached(hwnd, el) is not None
        return False
    except Exception:
        return False
def _web_has_field(hwnd) -> bool:
    """浏览器/Electron 窗口里，此刻光标是否落在一个输入控件上。\n\n    缓存交给 is_editable（TTL_DYNAMIC）统一管，这里不再单独缓存一层。\n    """
    try:
        return _is_field(_pick_element(hwnd))
    except Exception:
        return False
def is_editable(hwnd) -> bool:
    if not hwnd:
        return False
    else:
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return False
        else:
            blind = is_blind(hwnd)
            cls = get_class(hwnd)
            dynamic = blind or _class_is_web_host(cls)
            v = _cached(_cache_edit, hwnd, ttl=TTL_DYNAMIC if dynamic else TTL)
            if v is not None:
                return v
            else:
                proc = get_process_name(hwnd)
                ok = False
                if blind:
                    ok = _is_foreground(hwnd)
                else:
                    if cls in CLASSIC_EDITS:
                        ok = True
                    else:
                        if _class_is_web_host(cls):
                            ok = _web_has_field(hwnd)
                        else:
                            if cls in DOC_CLASSES:
                                ok = True
                            else:
                                if proc in APP_PROFILES:
                                    ok = True if APP_PROFILES[proc] == 'edit' else _uia_is_editable(hwnd)
                                else:
                                    if cls not in NEVER_EDIT:
                                        ok = _uia_is_editable(hwnd)
                _store(_cache_edit, hwnd, ok)
                return ok
def write_mode(hwnd) -> str:
    """决定读/写策略。\n\n    \"blind\" = 零无障碍的自绘程序（微信 4.x 这类）：读只能靠 Ctrl+A/Ctrl+C 抓取，\n    写只能靠 Ctrl+A/Ctrl+V 粘贴。\n\n    盲应用判定放在最前面：用户既然把它列进 blind_apps，就是要它走抓取通道，\n    不该因为某个子窗口恰好叫 \"Edit\" 又悄悄换回 WM_SETTEXT 路线。\n    """
    if is_blind(hwnd):
        return 'blind'
    else:
        cls = get_class(hwnd)
        if cls in CLASSIC_EDITS:
            return 'edit'
        else:
            if cls in DOC_CLASSES:
                return 'doc'
            else:
                proc = get_process_name(hwnd)
                if proc in APP_PROFILES:
                    return APP_PROFILES[proc]
                else:
                    return 'field'
def is_password(hwnd) -> bool:
    if get_class(hwnd) in CLASSIC_EDITS:
        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            return bool(style & win32con.ES_PASSWORD)
        except Exception:
            return False
    else:
        try:
            import uiautomation as auto
            el = auto.ControlFromHandle(hwnd)
            vp = el.GetPattern(auto.PatternId.ValuePattern) if el else None
            return bool(vp and vp.IsPassword)
        except Exception:
            return False
def _wm_gettext(hwnd, limit=8192):
    try:
        buf = ctypes.create_unicode_buffer(limit)
        n = user32.SendMessageW(hwnd, win32con.WM_GETTEXT, limit - 1, buf)
        return buf.value if n else ''
    except Exception:
        return None
def read_text(hwnd):
    if not hwnd:
        return
    else:
        mode = write_mode(hwnd)
        if mode == 'blind':
            return ''
        else:
            if mode == 'edit':
                t = _wm_gettext(hwnd)
                if t:
                    return t
                else:
                    u = _uia_value(hwnd)
                    if u:
                        return u
                    else:
                        return t if t is not None else ''
            else:
                if mode == 'doc':
                    return _uia_paragraph(hwnd)
                else:
                    return _uia_value(hwnd)
def _focused():
    """UIA 焦点元素。\n\n    原稿调的是 `uiautomation.GetFocusedElement()` —— 这个函数在 uiautomation 里**不存在**\n    （包里的名字是 `GetFocusedControl`）。AttributeError 被 `except Exception` 吞掉后\n    永远返回 None，于是所有走 UIA 的读写全部退化到 `ControlFromHandle(顶层窗口)`，\n    最后落到 `el.Name` —— 顶层窗口的 Name 就是**窗口标题**。\n    这就是\"镜像抓到的是窗口标题而不是输入内容\"的根因。\n    """
    import uiautomation as auto
    for name in ['GetFocusedControl', 'GetFocusedElement']:
        fn = getattr(auto, name, None)
        if fn is not None:
            try:
                return fn()
            except Exception:
                return
    return None
def _same_app(el, hwnd) -> bool:
    """焦点元素是否属于 hwnd 所在的那个应用。\n\n    判\"同进程\"，不判\"同 hwnd\"：浏览器里的输入框在 UIA 里 NativeWindowHandle 往往是 0，\n    按 hwnd 严格相等会把它拒掉，读到的就只剩顶层窗口的标题。\n    """
    try:
        return int(el.ProcessId) == get_pid(hwnd)
    except Exception:
        return False
def _pick_element(hwnd):
    """读/写文本时该用哪个 UIA 元素：焦点元素（同应用）优先，再退到 hwnd 自身元素。\n\n    焦点元素不是输入控件时（浏览器里停在 Document 上），往下钻一层找带键盘焦点的输入控件。\n    实测 Chromium 在光标落到 contenteditable 上时，GetFocusedControl() 直接返回那个\n    编辑器本身（不需要钻），所以子树搜索只是兜底，加了门槛和缓存。\n    """
    import uiautomation as auto
    _kick_and_settle(hwnd)
    focused = _focused()
    if focused is not None and _same_app(focused, hwnd):
        if _is_field(focused):
            return focused
        else:
            if _worth_walking(focused):
                deeper = _focused_field_cached(hwnd, focused)
                if deeper is not None:
                    return deeper
            return focused
    else:
        try:
            el = auto.ControlFromHandle(hwnd)
        except Exception:
            el = None
        if el is None:
            return
        else:
            if _is_field(el):
                return el
            else:
                if _worth_walking(el):
                    deeper = _focused_field_cached(hwnd, el)
                    if deeper is not None:
                        return deeper
                return el
DECOR_HINTS = ('placeholder', 'trailingbreak')
def _node_text(node, max_depth=3) -> str:
    """节点（含后代）的文字：TextPattern → Name → 往下收集子节点。

    必须往下收：实测占位符节点本身是个 GroupControl，既没有 TextPattern 也没有 Name，
    文字挂在它的子 TextControl 上（Cherry Studio 还多套了一层 GroupControl）。
    只读节点本身会拿到空串，占位符就永远去不掉，空聊天框会镜像出提示语。
    """
    try:
        import uiautomation as auto
        tp = node.GetPattern(auto.PatternId.TextPattern)
        if tp is not None:
            try:
                t = tp.DocumentRange.GetText(-1)
                if t:
                    return t
            except Exception:
                pass
        if node.Name:
            return node.Name
        if max_depth <= 0:
            return ''
        out = []
        try:
            kids = node.GetChildren()
        except Exception:
            kids = []
        for c in kids:
            t = _node_text(c, max_depth - 1)
            if t:
                out.append(t)
        return ''.join(out)
    except Exception:
        return ''
def _decor_nodes(el, max_depth=4, max_nodes=120):
    """找出编辑器里的装饰节点（占位提示语 / ProseMirror 尾随换行）。\n\n    实测 tiptap/ProseMirror 在 UIA 里的结构（Edge 与 Cherry Studio 一致）：\n      GroupControl cls=\'tiptap ProseMirror …\'        ← 输入框本体\n        GroupControl cls=\'placeholder has-focus\'     ← 编辑器为空时才有，\n          TextControl name=\'占位提示语…\'                 但它的文字会被本体的\n        TextControl cls=\'ProseMirror-trailingBreak\'      TextPattern 当正文读出来\n    用户一打字，ProseMirror 就把 placeholder 节点摘掉。\n    """
    out = []
    stack = [(el, 0)]
    n = 0
    while stack and n < max_nodes:
            node, d = stack.pop()
            n += 1
            if d > 0:
                try:
                    cn = str(node.ClassName or '')
                except Exception:
                    cn = ''
                key = cn.lower().replace('-', '').replace('_', '')
                for h in DECOR_HINTS:
                    if h in key:
                        out.append((h, _node_text(node)))
                        break
            if d < max_depth:
                try:
                    kids = node.GetChildren()
                except Exception:
                    kids = []
                for c in kids:
                    stack.append((c, d + 1))
    return out
def _strip_decorations(el, text: str) -> str:
    """把占位提示语和尾随 <br> 从镜像文本里去掉。\n\n    不处理的话，Cherry Studio 的空聊天框会镜像出「Agent 运行中 — Enter 排队发送…」\n    这类提示语 —— 用户看到的就是一段自己没打过的字，和抓到窗口标题一样是\"抓错东西\"。\n    """
    if not text:
        return ''
    else:
        try:
            decor = _decor_nodes(el)
        except Exception:
            return text
        for kind, t in decor:
            if kind == 'placeholder' and t and (t in text):
                        text = text.replace(t, '', 1)
        if any((k == 'trailingbreak' for k, _ in decor)) and text.endswith('\n'):
                text = text[:(-1)]
        if not text.strip():
            return ''
        else:
            return text
def _uia_value(hwnd):
    # irreducible cflow, using cdg fallback
    """读光标所在输入控件的文字。\n\n    只从「输入控件」读：焦点不在输入控件上时返回空串。\n    绝不退回 el.Name —— 顶层窗口的 Name 就是窗口标题；\n    也绝不退回 Document 的 Value —— 网页里那是网址（实测 Cherry Studio 的\n    RootWebArea：Value=\'file:///C:/Program%20Files/Cherry%20Stud…\'，\n    Text=整页正文含所有标签页标题和整段对话）。\n    镜像出标题/网址/整页正文比镜像出空白更糟：用户会认定程序在抓错东西。\n    """
    try:
        import uiautomation as auto
        el = _pick_element(hwnd)
        if el is None:
            return
        if not _is_field(el):
            return ''
        try:
            vp = el.GetPattern(auto.PatternId.ValuePattern)
        except Exception:
            vp = None
        if vp is not None:
            try:
                if not vp.IsReadOnly:
                    if vp.Value:
                        return vp.Value
            except Exception:
                pass
        try:
            tp = el.GetPattern(auto.PatternId.TextPattern)
            if tp is not None:
                return _strip_decorations(el, tp.DocumentRange.GetText(-1) or '')
        except Exception:
            return ''
        return ''
    except Exception:
        return
EXPAND_PARAGRAPH = 4
EP_START, EP_END = (0, 1)
SRC_CURRENT, SRC_BEGINNING, SRC_END = (0, 1, 2)
def _uia_paragraph(hwnd):
    # irreducible cflow, using cdg fallback
    """Word/WPS：只取当前段落，避免镜像整篇文档"""
    try:
        import uiautomation as auto
        el = _focused()
        if el is None:
            return
        tp = el.GetPattern(auto.PatternId.TextPattern)
        if tp is None:
            return
        rng = None
        try:
            sel = tp.GetSelection()
            if sel:
                rng = sel[0]
        except Exception:
            rng = None
        if rng is None:
            rng = tp.DocumentRange
        try:
            rng.Expand(EXPAND_PARAGRAPH)
        except Exception:
            pass
        txt = rng.GetText(-1)
        return txt.rstrip('\r\n') if txt else ''
    except Exception:
        return None
def top_title(hwnd) -> str:
    h = user32.GetAncestor(hwnd, 2)
    if not h:
        h = hwnd
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(h, buf, n + 2)
    return buf.value
def write_text(hwnd, text: str) -> tuple[bool, str, dict]:
    """返回 (成功?, 说明, 快照)；快照用于撤销/恢复"""
    if not hwnd:
        return (False, '目标输入框已失效', None)
    else:
        mode = write_mode(hwnd)
        proc = get_process_name(hwnd)
        snap = None
        if mode == 'doc':
            import word_bridge
            snap = word_bridge.snapshot(hwnd, proc, top_title(hwnd))
            ok, note, snap2 = word_bridge.replace_paragraph(hwnd, proc, top_title(hwnd), text, snap)
            if ok:
                return (True, note, snap2 or snap)
            else:
                return uia_replace_paragraph(text)
        else:
            if mode == 'edit':
                try:
                    buf = ctypes.create_unicode_buffer(text)
                    user32.SendMessageW(hwnd, win32con.WM_SETTEXT, 0, buf)
                    return (True, '已整段替换', {'mode': 'edit'})
                except Exception:
                    mode = 'field'
                else:
                    pass
            if mode == 'blind':
                ok, note, snap = replace_all_paste(text, hwnd)
                return (ok, note, dict(snap or {}, mode='blind'))
            else:
                return (True, '已整段替换', {'mode': 'field'}) if _uia_setvalue(hwnd, text) else replace_all_paste(text, hwnd)
def uia_replace_paragraph(text: str) -> tuple[bool, str, dict]:
    """UIA 兜底：选段落(排除段落标记) → Delete → 粘贴 → 光标回到译文末尾"""
    try:
        import uiautomation as auto
        el = _focused()
        tp = el.GetPattern(auto.PatternId.TextPattern) if el else None
        if tp is None:
            return _plain_paste(text)
        else:
            rng = None
            try:
                sel = tp.GetSelection()
                if sel:
                    rng = sel[0]
            except Exception:
                rng = None
            if rng is None:
                rng = tp.DocumentRange
            try:
                rng.Expand(EXPAND_PARAGRAPH)
            except Exception:
                pass
            try:
                rng.MoveEndpoint(EP_END, SRC_END, (-1))
            except Exception:
                pass
            try:
                original = rng.GetText((-1))
            except Exception:
                original = ''
            try:
                rng.Select()
            except Exception:
                pass
            time.sleep(0.04)
            press_key(VK_DELETE)
            time.sleep(0.04)
    except Exception:
        original = ''
    old = get_clipboard_text()
    if not set_clipboard_text(text):
        return (False, '剪贴板不可用', None)
    else:
        time.sleep(0.04)
        send_combo([VK_CONTROL], 86)
        time.sleep(0.1)
        _restore_clipboard_later(old)
        return (True, '已替换当前段落（UIA）' if original else '已插入光标处', {'mode': 'uia_doc', 'cn': original})
def _plain_paste(text) -> tuple[bool, str, dict]:
    old = get_clipboard_text()
    if not set_clipboard_text(text):
        return (False, '剪贴板不可用', None)
    else:
        time.sleep(0.04)
        send_combo([VK_CONTROL], 86)
        time.sleep(0.1)
        _restore_clipboard_later(old)
        return (True, '已插入光标处（未删除原内容）', {'mode': 'paste'})
def replace_all_paste(text: str, hwnd=None) -> tuple[bool, str, dict]:
    """整段替换 = Ctrl+A 全选 + Ctrl+V 粘贴。盲应用（微信）唯一的写回通道。\n\n    护栏与 grab_text 对称（v2.4）：模拟按键打到的是「当前键盘焦点」，不是 hwnd。\n    抓取打错只是读到别人的文字，写回打错是**把译文覆盖进别人的输入框**——\n    覆盖掉的东西用户往往无从撤销，所以这条路必须比抓取更严。\n    """
    if hwnd is not None:
        if not _is_foreground(hwnd):
            return (False, '目标窗口不在前台，写回会打到别的窗口，已取消', None)
        else:
            if not _focus_in_window(hwnd):
                return (False, '键盘焦点不在目标窗口里，写回会打到别的窗口，已取消', None)
    old = get_clipboard_text()
    if not set_clipboard_text(text):
        return (False, '剪贴板不可用', None)
    else:
        time.sleep(0.04)
        send_combo([VK_CONTROL], 65)
        time.sleep(0.05)
        send_combo([VK_CONTROL], 86)
        time.sleep(0.1)
        _restore_clipboard_later(old)
        return (True, '已整段替换（粘贴）', {'mode': 'field'})
def _restore_clipboard_later(old):
    if old is not None:
        threading.Timer(1.2, lambda: set_clipboard_text(old)).start()
def _focus_in_window(hwnd) -> bool:
    # irreducible cflow, using cdg fallback
    """键盘焦点是否落在 hwnd 所属的那个窗口里。\n\n    模拟按键是打到「当前键盘焦点」上的，不是打到 hwnd 上的。焦点在别的程序里时\n    照样发 Ctrl+A/Ctrl+C，抓回来的就是别人的内容 —— 那比抓不到更糟：用户会拿\n    一段错的译文去覆盖一段错的原文。\n    盲应用（微信）的 hwndFocus 恒为 0，这种拿不到信息的情况只能放行。\n    """
    try:
        root = user32.GetAncestor(hwnd, 2) or hwnd
        tid = user32.GetWindowThreadProcessId(root, None)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)) or not info.hwndFocus:
            return True
        f = info.hwndFocus
        return f == hwnd or (user32.GetAncestor(f, 2) or f) == root
    except Exception:
        return True
def reactivate(hwnd) -> bool:
    """把目标窗口拉回前台。托盘菜单触发抓取时必需。\n\n    点托盘菜单一定先把前台切到菜单上，而 grab_text 的护栏要求\"目标在前台\"\n    （这条护栏防的就是抓到别人的内容）。所以托盘这条路必须先把目标窗口\n    重新置回前台，再走同一条抓取通道。\n\n    SetForegroundWindow 受系统前台锁限制：非前台进程直接调会被拒绝，\n    AttachThreadInput 把调用线程和目标窗口线程临时绑一起是标准解法。\n    置前台是异步的，必须轮询确认，不能调完就当成功。\n    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    else:
        root = user32.GetAncestor(hwnd, 2) or hwnd
        if not user32.IsWindowVisible(root):
            user32.ShowWindow(root, 9)
        cur = user32.GetForegroundWindow()
        if cur == root or (cur and user32.GetAncestor(cur, 2) == root):
            return True
        else:
            tid_self = kernel32.GetCurrentThreadId()
            tid_tgt = user32.GetWindowThreadProcessId(root, None)
            if tid_tgt and tid_tgt != tid_self:
                    user32.AttachThreadInput(tid_self, tid_tgt, True)
    try:
        user32.BringWindowToTop(root)
        user32.SetForegroundWindow(root)
        user32.SetActiveWindow(root)
    finally:
        if tid_tgt and tid_tgt != tid_self:
                user32.AttachThreadInput(tid_self, tid_tgt, False)
    for _ in range(12):
        fg = user32.GetForegroundWindow()
        if fg == root or (fg and user32.GetAncestor(fg, 2) == root):
            return True
        else:
            time.sleep(0.05)
    return False
def grab_text(hwnd=None) -> tuple[str, str]:
    """盲应用取文：Ctrl+A → Ctrl+C → 读剪贴板。返回 (文本, 说明)。\n\n    为什么只有这一条路（全部实测过）：微信 4.x 的聊天输入区是自绘的\n    MMUIRenderSubWindowHW，UIA 全树只有 4 个节点且无任何 Pattern，\n    GetGUIThreadInfo 的 hwndFocus / hwndCaret 都是 0，WM_GETTEXT 只返回标题，\n    MSAA get_accChildCount 报「找不到元素」，置 SPI_SETSCREENREADER 后仍是 4 个节点。\n    剩下能拿到文字的只有注入 DLL（微信检测注入，不做）和剪贴板。\n\n    所以盲应用是**热键触发的一次性抓取**，不是实时镜像 —— 这一点必须在小窗上写清楚，\n    不能让用户以为程序坏了。\n\n    副作用：短暂占用剪贴板（1.2 秒后还原）；抓完按一下 End 收起全选，\n    免得用户下一个按键把整段内容替换掉。\n    """
    if hwnd is not None and (not _is_foreground(hwnd)):
        return ('', '目标窗口不在前台，抓取会打到别的程序上')
    else:
        if hwnd is not None and (not _focus_in_window(hwnd)):
            return ('', '键盘焦点不在目标窗口里，抓取会打到别的程序上')
        else:
            old = get_clipboard_text()
            if not set_clipboard_text(''):
                return ('', '剪贴板不可用')
            else:
                time.sleep(0.04)
                send_combo([VK_CONTROL], 65)
                time.sleep(0.06)
                send_combo([VK_CONTROL], 67)
                txt = ''
                deadline = time.time() + 1.6
                while time.time() < deadline:
                    txt = get_clipboard_text() or ''
                    if txt.strip():
                        break
                    time.sleep(0.08)
                press_key(VK_END)
                _restore_clipboard_later(old)
                if not txt.strip():
                    return ('', '没抓到内容：输入框是空的，或光标不在输入框里')
                else:
                    return (txt, f'已抓取 {len(txt)} 字')
def get_selection_text(hwnd) -> str:
    """非入侵读取「当前选中的文字」：UIA TextPattern.GetSelection，读不到返回 \"\"。\n\n    浏览器网页、Electron（含 QQNT 新版QQ）、Word/WPS、记事本这类暴露 UIA 的程序，\n    用户用鼠标划选后这里就能直接拿到选区——**不发按键、不碰剪贴板**，\n    所以自动监听（sel_watch）只对这条通道开放。\n    微信 4.x 这类零无障碍的自绘程序返回 \"\"，由调用方降级到 grab_selection()。\n    """
    if hwnd and is_blind(hwnd):
        return ''
    else:
        import uiautomation as auto
        def _walk(node):
            """从 node 起沿祖先链找第一个带 TextPattern 的元素，读它的选区。"""
            for _ in range(7):
                if node is None:
                    return ''
                else:
                    try:
                        tp = node.GetPattern(auto.PatternId.TextPattern)
                    except Exception:
                        tp = None
                    if tp is not None:
                        try:
                            ranges = tp.GetSelection()
                        except Exception:
                            ranges = []
                        for r in ranges or []:
                            try:
                                t = r.GetText((-1))
                            except Exception:
                                t = ''
                            if t and t.strip():
                                    return t
                    try:
                        node = node.GetParent()
                    except Exception:
                        node = None
            return ''
        node = None
        try:
            focused = _focused()
            if focused is not None and (not hwnd or _same_app(focused, hwnd)):
                    node = focused
        except Exception:
            node = None
        out = _walk(node)
        if out:
            return out
        else:
            GA_ROOT = 2
            starts = {hwnd}
            try:
                if hwnd:
                    starts.add(win32gui.GetAncestor(hwnd, GA_ROOT))
            except Exception:
                pass
            for h in starts:
                if not h or h == (node.NativeWindowHandle if node else 0):
                    continue
                else:
                    try:
                        el = auto.ControlFromHandle(h)
                    except Exception:
                        el = None
                    out = _walk(el)
                    if out:
                        return out
            return _legacy_selection()
def _legacy_selection() -> str:
    """传统 Win32 编辑控件的兜底：EM_GETSEL 取下标，WM_GETTEXT 取整文再切片。"""
    try:
        fg = user32.GetForegroundWindow()
        if not fg:
            return ''
        tid = user32.GetWindowThreadProcessId(fg, None)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not user32.GetGUIThreadInfo(tid, ctypes.byref(info)) or not info.hwndFocus:
            return ''
        hf = info.hwndFocus
        if get_class(hf) not in CLASSIC_EDITS:
            return ''
        sel = user32.SendMessageW(hf, 176, 0, 0)
        a, b = (sel & 65535, sel >> 16 & 65535)
        if b <= a or b - a > 20000:
            return ''
        full = _wm_gettext(hf, limit=200000)
        if not full or b > len(full):
            return ''
        return full[a:b]
    except Exception:
        return ''
def grab_selection(hwnd=None) -> tuple[str, str]:
    """划词降级通道：Ctrl+C 复制**用户的选区**（不是 Ctrl+A 全选），读剪贴板后还原。\n\n    给微信/旧QQ 这类 UIA 读不到选区的自绘程序用。与 grab_text 同款的护栏：\n    目标不在前台、键盘焦点不在目标窗口 → 一个模拟按键都不发，直接拒绝。\n    只发 Ctrl+C 不发 Ctrl+A：用户已经划好词了，全选会把他的选区改掉。\n    """
    if hwnd is not None and (not _is_foreground(hwnd)):
        return ('', '目标窗口不在前台，复制选区会打到别的程序')
    else:
        if hwnd is not None and (not _focus_in_window(hwnd)):
            return ('', '键盘焦点不在目标窗口里，复制选区会打到别的程序')
        else:
            old = get_clipboard_text()
            if not set_clipboard_text(''):
                return ('', '剪贴板不可用')
            else:
                time.sleep(0.04)
                send_combo([VK_CONTROL], 67)
                txt = ''
                deadline = time.time() + 1.6
                while time.time() < deadline:
                    txt = get_clipboard_text() or ''
                    if txt.strip():
                        break
                    time.sleep(0.08)
                _restore_clipboard_later(old)
                if not txt.strip():
                    return ('', '没读到选区：先用鼠标/键盘选中一段文字，再按划词热键')
                else:
                    return (txt.strip(), f'已复制选区 {len(txt.strip())} 字')
def undo_replace(hwnd, snap, original) -> tuple[bool, str]:
    """撤销一次替换：Word/WPS 走原生撤销栈并校验；其它直接写回原中文"""
    if not hwnd:
        return (False, '目标窗口已失效')
    else:
        mode = write_mode(hwnd)
        proc = get_process_name(hwnd)
        if mode == 'doc':
            import word_bridge
            title = top_title(hwnd)
            ok, note = word_bridge.undo_last(hwnd, proc, title, snap, original)
            if ok:
                return (True, note)
            else:
                if original:
                    ok2, note2 = word_bridge.restore_original(hwnd, proc, title, snap, original)
                    return (ok2, f'{note} → {note2}')
                else:
                    return (False, note)
        else:
            if original:
                ok, note, _ = write_text(hwnd, original)
                return (ok, f'已写回中文原文（{note}）')
            else:
                return (False, '没有可恢复的原文')
def _uia_setvalue(hwnd, text) -> bool:
    try:
        import uiautomation as auto
        el = _pick_element(hwnd)
        if el is None:
            return False
        vp = el.GetPattern(auto.PatternId.ValuePattern)
        if vp is not None and (not vp.IsReadOnly):
            vp.SetValue(text)
            return True
        return False
    except Exception:
        return False
def get_clipboard_text():
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return None
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass
        time.sleep(0.03)
    return None
def set_clipboard_text(text: str) -> bool:
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()
            return True
        except Exception:
            pass
        time.sleep(0.03)
    return False
INPUT_KEYBOARD, KEYEVENTF_KEYUP = (1, 2)
VK_DELETE = 46
VK_END = 35
VK_CONTROL, VK_SHIFT, VK_MENU = (17, 16, 18)
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]
class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]
class _U(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]
class INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('iu', _U)]
def _send(items):
    user32.SendInput(len(items), (INPUT * len(items))(*items), ctypes.sizeof(INPUT))
def press_key(vk, up=False):
    i = INPUT()
    i.type = INPUT_KEYBOARD
    i.iu.ki.wVk = vk
    i.iu.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    _send([i])
def send_combo(mods, vk):
    for m in mods:
        press_key(m, False)
    press_key(vk, False)
    press_key(vk, True)
    for m in reversed(mods):
        press_key(m, True)
def caret_screen_pos():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return
    else:
        tid = user32.GetWindowThreadProcessId(hwnd, None)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndCaret:
            pt = wintypes.POINT(info.rcCaret.left, info.rcCaret.top)
            user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt))
            return (pt.x, pt.y)
        else:
            f = get_focus_hwnd()
            if f:
                r = wintypes.RECT()
                if user32.GetWindowRect(f, ctypes.byref(r)):
                    return (r.left, r.bottom + 6)
            return None
def cursor_screen_pos():
    """鼠标当前位置。\n\n    盲应用（微信这类）拿不到系统光标矩形 —— 实测 GetGUIThreadInfo 的 hwndCaret\n    是 0、rcCaret 全 0 —— 退而求其次用鼠标位置：用户刚点过输入框，\n    小窗弹在鼠标旁边比弹在窗口左下角有用得多。\n    """
    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        return (pt.x, pt.y)
    else:
        return None