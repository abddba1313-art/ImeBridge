# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'main.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""讯飞输入法 · 中英翻译桥 v2.5\n\nv2.5 三件事（用户反馈）：\n1. 目标语言新增葡萄牙文/吉尔吉斯文/哈萨克文/乌兹别克文/维吾尔文，老配置自动补齐；\n2. 修小窗「语言下拉框点开就闪退、选了保不住」：readonly Combobox 的下拉列表\n   要键盘焦点，小窗 WS_EX_NOACTIVATE 给不了；原生菜单抓取实测同样点了弹不出\n   ——最终改成**自绘列表窗** popup.open_lang_picker（同款 NOACTIVATE 窗，tk 普通控件点击）；\n3. 新增划词翻译：UIA 暴露选区的程序（网页/Electron/QQNT/Word/记事本）划词自动弹译文；\n   微信这类零无障碍程序按 Ctrl+Alt+Shift+D 降级复制选区。两条通道都不抢焦点。\n\nv2.3 三处修复（都是用户真机反馈 + 本机实测定位）：\n1. 热键：v2.2 注册失败就静默跳过，本机实测 4 个组合全被占用 → 一个都没挂上，\n   按 Ctrl+Alt+T 弹的是别人的截图框。现在注册结果必须上报、占用自动换空闲键。\n2. 云端服务：补 API Key（带 Authorization 头 + 401 可操作提示），Key 落盘加密。\n3. 配置：托盘「设置…」开可视窗口，改完即生效，不再要求用户编辑 config.json。\n"""
import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autostart
import seltrans
import text_io
from config import config_dir, config_path, load_config, log_path, save_config
from hotkeys import HotkeyManager
from popup import Popup
from seltrans import SelPopup, selection_should_translate
from settings import build_settings_window
from tray import start_tray
from translator import TranslateError, Translator
MUTEX = 'Local\\ImeBridge_Single_Mutex'
def single_instance() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX)
    return ctypes.windll.kernel32.GetLastError() != 183
def log(msg: str):
    try:
        with open(log_path(), 'a', encoding='utf-8') as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass
def has_cjk(s: str) -> bool:
    return any(('一' <= c <= '鿿' for c in s))
class Bridge:
    def __init__(self, root: tk.Tk, cfg):
        self.root, self.cfg = (root, cfg)
        self.q = queue.Queue()
        self.translator = Translator(cfg)
        self.current_hwnd = None
        self.current_text = ''
        self.source_cn = ''
        self.translated = ''
        self.replaced_active = False
        self.paused = False
        self.pinned = False
        self._busy = False
        self.last_change = time.time()
        self.history = []
        self.blind_active = False
        self.hotkey_status = {}
        self.settings_win = None
        text_io.set_a11y_kick(getattr(cfg, 'kick_accessibility', True))
        text_io.set_blind_apps(getattr(cfg, 'blind_apps', None))
        self.popup = Popup(root, cfg, {'translate': lambda: self.do_translate(), 'replace': lambda: self.do_replace(), 'copy': lambda: self.do_copy(), 'close': lambda: self.do_close(), 'lang': lambda: self.on_lang_change(), 'auto': lambda: self.on_auto_change(), 'undo': lambda: self.do_undo(), 'restore_cn': lambda: self.do_restore_cn(), 'grab': lambda: self.do_grab()})
        self.sel = SelPopup(root, cfg, {'copy': lambda *a: self.do_sel_copy(), 'close': lambda *a: self.do_sel_close(), 'dir': lambda *a: self.on_sel_direction(), 'resize': lambda *a: self.on_sel_resize()})
        self.sel_busy = False
        self._sel_pending = None
        self._sel_last = ''
        self._sel_last_poll = 0.0
        self._sel_oversize_noted = ''
        self.hotkeys = HotkeyManager(cfg, self.on_hotkey, on_status=lambda st: self.q.put(('hotkeys', st)))
        self.tray = start_tray(self)
        threading.Thread(target=self.watch_loop, daemon=True).start()
        threading.Thread(target=self.health_loop, daemon=True).start()
        root.after(50, self.ui_tick)
        if cfg.autostart:
            autostart.enable()
    def _poll_sel(self, hwnd):
        """监听线程里读选区（UIA 通道，非入侵）。同一选区要稳定 0.3 秒才触发，
        防拖拽途中的中间状态被翻译。判据全在 seltrans.selection_should_translate（纯函数）。"""
        if not getattr(self.cfg, 'sel_watch', False) or self.paused:
            return
        now = time.time()
        if now - self._sel_last_poll < max(0.15, self.cfg.sel_poll_ms / 1000.0):
            return
        self._sel_last_poll = now
        try:
            s = (text_io.get_selection_text(hwnd) or '').strip()
        except Exception:
            s = ''
        if not s:
            if getattr(self.cfg, 'kick_accessibility', True):
                try:
                    text_io.ensure_a11y(hwnd)
                except Exception:
                    pass
            self._sel_pending = None
            return
        if s == self._sel_last and self.sel.visible:
            return
        if self._sel_pending and self._sel_pending[0] == s:
            if not (now - self._sel_pending[1] >= 0.3 and not self.sel_busy and not self._busy):
                return
            self._sel_pending = None
            if selection_should_translate(s, self.cfg, self.translated, self.source_cn):
                self._sel_last = s
                self.q.put(('sel', s, text_io.cursor_screen_pos()))
                return
            if len(s) > int(getattr(self.cfg, 'sel_max_chars', 1000) or 1000) and s != getattr(self, '_sel_oversize_noted', ''):
                self._sel_oversize_noted = s
                self._sel_last = s
                self.q.put(('sel_oversize', s, text_io.cursor_screen_pos()))
            return
        self._sel_pending = (s, now)
    def watch_loop(self):
        last_hwnd, last_text, last_pos = (None, None, None)
        while True:
            if self.paused:
                time.sleep(0.3)
                continue
            else:
                hwnd = text_io.get_focus_hwnd()
                self._poll_sel(hwnd)
                if not text_io.is_editable(hwnd):
                    if last_hwnd is not None:
                        self.q.put(('blur',))
                        self.q.put(('blindmode', False, ''))
                        last_hwnd, last_text = (None, None)
                        self.blind_active = False
                    time.sleep(0.25)
                    continue
                else:
                    if text_io.is_password(hwnd) and (not self.cfg.mirror_password):
                            self.q.put(('info', '密码框：已跳过镜像'))
                            time.sleep(0.25)
                            continue
                    blind = text_io.write_mode(hwnd) == 'blind'
                    if hwnd != last_hwnd:
                        last_hwnd, last_text = (hwnd, None)
                        self.current_hwnd = hwnd
                        self.blind_active = blind
                        self.q.put(('blindmode', blind, text_io.get_process_name(hwnd)))
                        if self.cfg.auto_show:
                            pos = text_io.cursor_screen_pos() if blind else text_io.caret_screen_pos()
                            last_pos = pos
                            self.q.put(('show', pos))
                    if blind:
                        self.q.put(('idle', (time.time() - self.last_change) * 1000, 0, True))
                        time.sleep(self.cfg.poll_slow_ms / 1000.0)
                        continue
                    else:
                        text = text_io.read_text(hwnd) or ''
                        changed = text != last_text
                        if changed:
                            last_text = text
                            self.last_change = time.time()
                            self.q.put(('text', text))
                        if self.cfg.follow_caret:
                            pos = text_io.caret_screen_pos()
                            if pos and (last_pos is None or abs(pos[0] - last_pos[0]) > self.cfg.caret_follow_px or abs(pos[1] - last_pos[1]) > self.cfg.caret_follow_px):
                                    last_pos = pos
                                    self.q.put(('move', pos))
                        self.q.put(('idle', (time.time() - self.last_change) * 1000, len(text.strip()), False))
                        time.sleep((self.cfg.poll_fast_ms if changed else self.cfg.poll_slow_ms) / 1000.0)
    def ui_tick(self):
        events = []
        try:
            while True:
                events.append(self.q.get_nowait())
        except queue.Empty:
            pass
        for ev in events:
            k = ev[0]
            try:
                if k == 'text':
                    self._on_mirror(ev[1])
                else:
                    if k == 'show':
                        p = ev[1]
                        self.popup.show(p[0] if p else 120, p[1] + 20 if p else 120)
                    else:
                        if k == 'move':
                            if self.popup.visible:
                                self.popup.show(ev[1][0], ev[1][1] + 20)
                        else:
                            if k == 'blur':
                                if not self.pinned:
                                    self.popup.hide()
                            else:
                                if k == 'idle':
                                    idle_ms, n = (ev[1], ev[2])
                                    blind = ev[3] if len(ev) > 3 else False
                                    self.popup.show_actions(blind or (idle_ms >= self.cfg.idle_ms and n > 0 and (not self._busy)))
                                else:
                                    if k == 'blindmode':
                                        self.popup.set_blind_mode(ev[1], ev[2] if len(ev) > 2 else '')
                                    else:
                                        if k == 'grabbed':
                                            self.do_translate(text=ev[1])
                                        else:
                                            if k == 'sel':
                                                self._show_selection(ev[1], ev[2])
                                            else:
                                                if k == 'sel_oversize':
                                                    s = ev[1]
                                                    self.sel.show(*(ev[2] if ev[2] else (None, None)))
                                                    self.sel.set_source(s)
                                                    self.sel.set_direction(self.cfg.sel_source_lang, self.cfg.sel_target_lang)
                                                    self.sel.set_result('')
                                                    self.sel.set_status('选区 %d 字，超过自动上限 %d —— 按 %s 强制翻译' % (len(s), int(getattr(self.cfg, 'sel_max_chars', 1000) or 1000), (self.cfg.hotkey_selection or '划词热键').upper()), '#ffd166')
                                                else:
                                                    if k == 'sel_done':
                                                        self.sel.set_result(ev[1])
                                                        self.sel.set_status('可复制译文', '#7bd88f')
                                                        self.sel_busy = False
                                                    else:
                                                        if k == 'sel_err':
                                                            self.sel.set_status(ev[1], '#ff6b6b')
                                                            self.sel_busy = False
                                                        else:
                                                            if k == 'progress':
                                                                self.popup.set_status(ev[1], '#ffd166')
                                                            else:
                                                                if k == 'translated':
                                                                    self.translated = ev[1]
                                                                    self.popup.set_result(ev[1])
                                                                    self.popup.set_status(self._write_back_hint(), '#7bd88f')
                                                                    self.popup.show_actions(True)
                                                                    self._busy = False
                                                                else:
                                                                    if k == 'error':
                                                                        self.popup.set_status(ev[1], '#ff6b6b')
                                                                        self.popup.show_actions(True)
                                                                        self._busy = False
                                                                    else:
                                                                        if k == 'undone':
                                                                            self.popup.set_status(ev[1], '#7bd88f')
                                                                            self.popup.show_undo_row(False)
                                                                            self.replaced_active = False
                                                                        else:
                                                                            if k == 'info':
                                                                                self.popup.set_status(ev[1])
                                                                            else:
                                                                                if k == 'svc':
                                                                                    if self.tray:
                                                                                        try:
                                                                                            self.tray.update_menu()
                                                                                        except Exception:
                                                                                            pass
                                                                                        else:
                                                                                            pass
                                                                                else:
                                                                                    if k == 'hotkeys':
                                                                                        self._on_hotkey_status(ev[1])
            except Exception as e:
                log(f'ui_tick: {e}')
        self.root.after(50, self.ui_tick)
    def _on_mirror(self, text: str):
        """镜像刷新时维护「中文原文」不被英文写回覆盖"""
        self.current_text = text
        self.popup.set_text(self._mirror(text))
        t = text.strip()
        if self.translated and t == self.translated.strip():
            self.replaced_active = True
            self.popup.set_status('已替换，可「撤销替换」', '#7bd88f')
            self.popup.show_undo_row(True, f'历史 {len(self.history)} 条')
        else:
            if has_cjk(text):
                self.source_cn = text
                self.replaced_active = False
                if self.translated:
                    self.translated = ''
                    self.popup.clear_result()
            else:
                if t:
                    self.source_cn = text
    def _mirror(self, text: str) -> str:
        if len(text) > self.cfg.max_chars:
            return text[:self.cfg.max_chars] + ' …'
        else:
            return text
    def do_grab(self, then_translate=True):
        """微信这类零无障碍程序：Ctrl+A/Ctrl+C 抓一次输入框内容，然后翻译。\n\n        实时镜像在这些程序里做不到（实测 UIA 全树 4 个节点、无任何 Pattern，\n        hwndFocus/hwndCaret 都是 0，WM_GETTEXT 只返回标题，MSAA 也是空的），\n        所以做成显式的一次性抓取，并在小窗上写清楚，不让用户以为程序坏了。\n        """
        if self._busy:
            self.popup.set_status('正在翻译，请稍候再抓取', '#ffd166')
            return
        else:
            hwnd = self.current_hwnd or text_io.get_focus_hwnd()
            self._busy = True
            self.popup.set_status('正在抓取输入框内容…', '#ffd166')
            def worker():
                try:
                    txt, note = text_io.grab_text(hwnd)
                except Exception as e:
                    txt, note = ('', f'抓取异常：{e}')
                if not txt:
                    self._busy = False
                    self.q.put(('error', note))
                    log(f'grab fail: {note}')
                    return
                else:
                    log(f'grab ok {len(txt)}字')
                    self.q.put(('text', txt))
                    if then_translate:
                        self.q.put(('grabbed', txt))
                        return
                    else:
                        self._busy = False
                        self.q.put(('info', note))
            threading.Thread(target=worker, daemon=True).start()
    def _show_selection(self, sel: str, pos=None):
        """悬浮窗亮出原文并发起翻译（自动通道和热键通道共用这一个出口）。\n\n        v2.5.2：方向取悬浮窗自己的双选框，不再固定\"中文→X\"。\n        v2.7：双选框存的是划词**独立**的一对键（cfg.sel_source_lang →\n        cfg.sel_target_lang），与镜像小窗的 source_lang/target_lang 互不干涉。\n        源=目标时不发起请求（自己译自己没有意义）。\n        """
        self.sel.show(*(pos if pos else (None, None)))
        self.sel.set_source(sel)
        self._sel_oversize_noted = ''
        src_lang = self.cfg.sel_source_lang or '中文'
        target = self.cfg.sel_target_lang
        self.sel.set_direction(src_lang, target)
        if not seltrans.direction_needs_translation(src_lang, target):
            self.sel.set_result(sel)
            self.sel.set_status('源语言=目标语言，未翻译', '#ff6b6b')
            self.sel_busy = False
            return
        else:
            self.sel.set_status('翻译中…', '#ffd166')
            self.sel_busy = True
            def worker():
                import translator
                try:
                    max_len = max(40, self.cfg.chunk_size)
                    overflow = 0
                    if max_len < 300 and (self.translator.nllb_route(target, src_lang) or self.translator.polish_route(target, src_lang)):
                            max_len, overflow = (300, 150)
                    chunks = translator.split_chunks(sel, max_len, overflow)
                    outs = []
                    for i, c in enumerate(chunks, 1):
                        outs.append(self.translator.translate(c, target, src_lang))
                        if i < len(chunks):
                            self.q.put(('sel_done', ''.join(outs)))
                    self.q.put(('sel_done', ''.join(outs)))
                except translator.TranslateError as e:
                    self.q.put(('sel_err', str(e)))
                except Exception as e:
                    self.q.put(('sel_err', f'翻译异常：{e}'))
            threading.Thread(target=worker, daemon=True).start()
    def on_sel_resize(self):
        """拖角松手：尺寸写回配置落盘，下次启动保持用户拉出来的大小。"""
        w, h = self.sel.current_size()
        self.cfg.sel_win_w, self.cfg.sel_win_h = (w, h)
        save_config(self.cfg)
        log('sel window resized to %dx%d' % (w, h))
    def on_sel_direction(self):
        """双选框点选：落盘划词**自己的**方向 → 窗里已有原文就立即重译。\n\n        v2.7：默认解耦——不再写 source_lang/target_lang、不再同步镜像小窗显示；\n        设置里勾上「划词与镜像语言联动」（sel_link_langs）才恢复 v2.5.2 的双向联动。\n        """
        src, tgt = self.sel.direction()
        self.cfg.sel_source_lang, self.cfg.sel_target_lang = (src, tgt)
        if getattr(self.cfg, 'sel_link_langs', False):
            self.cfg.source_lang, self.cfg.target_lang = (src, tgt)
            try:
                self.popup.lang_var.set(tgt)
            except Exception:
                pass
        save_config(self.cfg)
        log('sel direction: %s -> %s' % (src, tgt))
        text = self.sel.current_source()
        if self.sel.visible and text and (not self.sel_busy):
            self._show_selection(text)
        else:
            if text:
                self.sel.set_status('方向已更新：%s → %s' % (src, tgt), '#7bd88f')
    def do_selection_translate(self):
        """第 5 把热键：划词翻译（微信/旧QQ 这类读不到选区的程序的兜底通道）。\n\n        先走 UIA（非入侵）；读不到才降级复制选区（grab_selection 自带前台护栏，\n        目标不在前台时一个按键都不发）。\n        """
        if self.sel_busy:
            return
        else:
            hwnd = self.current_hwnd or text_io.get_focus_hwnd()
            self.sel_busy = True
            if not self.sel.visible:
                pos = text_io.cursor_screen_pos()
                self.sel.show(*(pos if pos else (None, None)))
                self.sel.set_status('读取选区…', '#ffd166')
            def worker():
                sel = ''
                try:
                    sel = (text_io.get_selection_text(hwnd) or '').strip()
                except Exception:
                    sel = ''
                note = ''
                if not sel:
                    sel, note = text_io.grab_selection(hwnd)
                if not sel:
                    self._sel_last = ''
                    self.q.put(('sel_err', note or '没读到选区：先选中一段文字再按热键'))
                    return
                else:
                    self._sel_last = sel
                    self.q.put(('sel', sel, text_io.cursor_screen_pos()))
            threading.Thread(target=worker, daemon=True).start()
    def do_sel_copy(self):
        t = self.sel.current_result()
        if t:
            text_io.set_clipboard_text(t)
            self.sel.set_status('译文已复制', '#7bd88f')
    def do_sel_close(self):
        self.sel.hide()
        self._sel_last = ''
        self.sel_busy = False
    def sel_from_tray(self):
        """托盘入口：先把目标窗口拉回前台（点菜单会抢前台），再走同一条划词通道。"""
        hwnd = self.current_hwnd
        if hwnd and (not text_io.reactivate(hwnd)):
            self.q.put(('sel_err', '目标窗口没能回到前台：点一下目标窗口再按划词热键'))
        else:
            self.do_selection_translate()
    def do_translate(self, text=None, target=None):
        src = (text if text is not None else self.source_cn or self.current_text).strip()
        if len(src) < 1:
            if self.blind_active:
                self.do_grab()
                return
            else:
                self.popup.set_status('没有可翻译的内容', '#ff6b6b')
                return
        else:
            target = target or self.popup.target_lang()
            if target == '中文':
                self.popup.set_status('镜像输入本身就是中文，目标请换一种语言', '#ff6b6b')
                return
            else:
                self._busy = True
                self.popup.show_actions(False)
                self.popup.set_status(f'准备翻译 → {target}', '#ffd166')
                self.popup.clear_result()
                def worker():
                    def prog(m):
                        self.q.put(('progress', m))
                    try:
                        out = self.translator.translate_long(src, target, prog, source='中文')
                        self.q.put(('translated', out))
                        log(f'translate ok {len(src)}字 -> {len(out)}字符 / {target}')
                    except TranslateError as e:
                        self.q.put(('error', str(e)))
                    except Exception as e:
                        self.q.put(('error', f'翻译异常：{e}'))
                        log(f'translate crash: {e}')
                        return None
                threading.Thread(target=worker, daemon=True).start()
    def _write_back_hint(self) -> str:
        """译文就绪后的提示：抓取模式里把生效的写回热键一起说出来。\n\n        抓取模式比正常模式多一行「抓取行」，v2.3 的小窗高度写死，操作条被顶出窗口\n        → 用户看不到「替换输入框」按钮，也没有第二条出路。现在两条都摆出来。\n        """
        try:
            hk = self.effective_hotkey(3) or ''
        except Exception:
            hk = ''
        if self.blind_active and hk:
            return f'点「替换输入框」或按 {hk.upper()} 写回'
        else:
            return '点「替换输入框」写回'
    def do_replace(self):
        en = self.translated or self.popup.current_result()
        if not en:
            self.popup.set_status('还没有译文', '#ff6b6b')
            return
        else:
            hwnd = text_io.get_focus_hwnd()
            if not text_io.is_editable(hwnd):
                hwnd = self.current_hwnd
            ok, note, snap = text_io.write_text(hwnd, en)
            self.popup.set_status(note, '#7bd88f' if ok else '#ff6b6b')
            log(f'replace ok={ok} note={note}')
            if ok:
                self.history.append({'cn': self.source_cn, 'en': en, 'snap': snap, 'lang': self.popup.target_lang(), 'hwnd': hwnd, 'ts': time.time()})
                self.history = self.history[-self.cfg.history_size:]
                self.popup.show_undo_row(True, f'历史 {len(self.history)} 条')
                self.pinned = True
                self._busy = False
            else:
                if self.blind_active:
                    self.popup.set_status(f'{note}；把光标放回输入框再试', '#ff6b6b')
                self._busy = False
    def do_undo(self):
        if not self.history:
            self.popup.set_status('没有可撤销的记录', '#ff6b6b')
            return
        else:
            h = self.history[(-1)]
            hwnd = text_io.get_focus_hwnd()
            if not text_io.is_editable(hwnd):
                hwnd = h.get('hwnd')
            self.popup.set_status('撤销中…', '#ffd166')
            def worker():
                try:
                    ok, note = text_io.undo_replace(hwnd, h.get('snap'), h.get('cn'))
                    if ok:
                        self.history.pop()
                        self.source_cn = h.get('cn', '')
                        self.translated = ''
                        self.q.put(('undone', note))
                        self.q.put(('text', h.get('cn', '')))
                    else:
                        self.q.put(('error', note))
                except Exception as e:
                    self.q.put(('error', f'撤销异常：{e}'))
            threading.Thread(target=worker, daemon=True).start()
    def do_restore_cn(self):
        if not self.history:
            self.popup.set_status('没有可恢复的原文', '#ff6b6b')
            return
        else:
            h = self.history[(-1)]
            hwnd = text_io.get_focus_hwnd()
            if not text_io.is_editable(hwnd):
                hwnd = h.get('hwnd')
            def worker():
                ok, note, _ = text_io.write_text(hwnd, h.get('cn', ''))
                self.q.put(('undone' if ok else 'error', '已恢复中文原文' if ok else note))
                if ok:
                    self.history.pop()
            threading.Thread(target=worker, daemon=True).start()
    def on_lang_change(self):
        lang = self.popup.target_lang()
        self.cfg.target_lang = lang
        if getattr(self.cfg, 'sel_link_langs', False):
            self.cfg.sel_source_lang = self.cfg.source_lang
            self.cfg.sel_target_lang = lang
            self.sel.set_direction(self.cfg.source_lang, lang)
        save_config(self.cfg)
        src = self.source_cn.strip()
        if self.popup.auto_retranslate():
            if self._busy:
                self.popup.set_status('正在翻译，稍后再选语言', '#ffd166')
                return
            else:
                if len(src) >= self.cfg.retranslate_min_chars:
                    self.popup.set_status(f'自动重译为「{lang}」…', '#ffd166')
                    self.do_translate(text=src, target=lang)
                else:
                    self.popup.set_status(f'目标语言：{lang}（中文太短，未自动重译）')
        else:
            self.popup.set_status(f'目标语言已设为「{lang}」，下次点翻译生效', '#7bd88f')
    def on_auto_change(self):
        self.cfg.auto_retranslate = self.popup.auto_retranslate()
        save_config(self.cfg)
        self.popup.set_status('选语言后自动重译：' + ('开' if self.cfg.auto_retranslate else '关'), '#7bd88f')
    def do_copy(self):
        t = self.translated or self.popup.current_result()
        if t:
            text_io.set_clipboard_text(t)
            self.popup.set_status('译文已复制', '#7bd88f')
    def do_close(self):
        self.pinned = False
        self.popup.hide()
    def health_loop(self):
        while True:
            ok, info = self.translator.health()
            self.translator.nllb_health()
            self.q.put(('svc', ok, info))
            time.sleep(self.cfg.health_interval_s)
    def on_hotkey(self, hid: int):
        if hid == 1:
            if self.blind_active and getattr(self.cfg, 'blind_auto_grab', True):
                self.do_grab()
            else:
                self.do_translate()
        else:
            if hid == 2:
                self.toggle()
            else:
                if hid == 3:
                    self.do_replace()
                else:
                    if hid == 4:
                        self.do_undo()
                    else:
                        if hid == 5:
                            self.do_selection_translate()
    def toggle(self):
        if self.popup.visible:
            self.pinned = False
            self.popup.hide()
        else:
            self.pinned = True
            self.popup.show(140, 140)
    def toggle_pause(self):
        self.paused = not self.paused
    def toggle_follow(self):
        self.cfg.follow_caret = not self.cfg.follow_caret
        save_config(self.cfg)
    def toggle_auto(self):
        self.cfg.auto_retranslate = not self.cfg.auto_retranslate
        self.popup.auto_var.set(self.cfg.auto_retranslate)
        save_config(self.cfg)
    def toggle_autostart(self):
        autostart.disable() if autostart.is_enabled() else autostart.enable()
        self.cfg.autostart = autostart.is_enabled()
        save_config(self.cfg)
    def autostart_enabled(self) -> bool:
        return autostart.is_enabled()
    def _on_hotkey_status(self, st: dict):
        """注册结果必须让用户看见：小窗状态条 + 托盘 + 日志，三处一起说。"""
        self.hotkey_status = dict(st or {})
        summary = self.hotkeys.summary()
        log(summary)
        eff = self.hotkey_status.get(1, {}).get('effective', '')
        if eff:
            self.popup.set_hotkey_text(eff)
        bad = [h for h in [1, 2, 3, 4] if not (self.hotkey_status.get(h) or {}).get('ok')]
        moved = [h for h in [1, 2, 3, 4] if (self.hotkey_status.get(h) or {}).get('changed')]
        if bad:
            self.popup.set_status('热键注册失败，见托盘/设置', '#ff6b6b')
        else:
            if moved:
                self.popup.set_status('热键已自动改用空闲键，见设置', '#ffd166')
        if self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass
    def hotkey_state(self) -> dict:
        return dict(self.hotkey_status)
    def effective_hotkey(self, hid: int) -> str:
        return (self.hotkey_status.get(hid) or {}).get('effective', '')
    def open_settings(self):
        # irreducible cflow, using cdg fallback
        """托盘「设置…」入口。已开着就把它提到最前，不重复开。"""
        try:
            if self.settings_win is not None:
                try:
                    self.settings_win.lift()
                    self.settings_win.focus_force()
                    return self.settings_win
                except Exception:
                    self.settings_win = None
            self.settings_win = build_settings_window(self.root, self.cfg, {'saved': self.on_settings_saved, 'hotkey_status': self.hotkey_state, 'test_service': self.probe_service})
            return self.settings_win
        except Exception as e:
            log(f'open_settings: {e}')
            return None
    def on_settings_saved(self, cfg):
        """保存即生效：落盘 → 热键重注册 → 唤醒开关 → 抓取名单 → 界面文案。"""
        save_config(cfg)
        self.hotkeys.reload(cfg)
        text_io.set_a11y_kick(getattr(cfg, 'kick_accessibility', True))
        text_io.set_blind_apps(getattr(cfg, 'blind_apps', None))
        self.popup.set_languages(list(cfg.languages))
        self.popup.lang_var.set(cfg.target_lang)
        self.popup.refresh_actions()
        if getattr(cfg, 'sel_link_langs', False):
            cfg.sel_source_lang, cfg.sel_target_lang = (cfg.source_lang, cfg.target_lang)
            save_config(cfg)
        self.sel.set_language_lists(list(cfg.languages))
        self.sel.set_direction(cfg.sel_source_lang, cfg.sel_target_lang)
        if cfg.autostart:
            autostart.enable()
        else:
            autostart.disable()
        self.cfg = cfg
        self.translator.cfg = cfg
    def probe_service(self, draft):
        """设置窗口「测试连接」用的探针：用草稿配置真连一次，不动运行中的翻译器。"""
        from translator import Translator as T
        t = T(draft)
        return t.health()
    def open_config_json(self):
        try:
            os.startfile(config_path())
        except Exception:
            return None
    def open_config(self):
        """托盘旧入口名保留：语义从\"打开 json\"改成\"打开设置窗口\"。"""
        self.open_settings()
    def open_log_dir(self):
        try:
            os.startfile(config_dir())
        except Exception:
            return None
    def test_translate(self):
        self.do_translate(text='今天天气很好，我们一起去公园散步。')
    def grab_from_tray(self):
        """托盘菜单触发的「抓取并翻译」。\n\n        点托盘菜单会把前台切到菜单上，直接抓取会因\"目标不在前台\"被拒绝\n        （这条护栏是 v2.2 加的，防的正是抓到别人的内容）。\n        所以先把记住的目标窗口重新置前台，再走同一条抓取通道。\n        """
        hwnd = self.current_hwnd
        if hwnd and (not text_io.reactivate(hwnd)):
            self.popup.set_status('目标窗口没能回到前台，请点一下微信输入框再按热键', '#ff6b6b')
            self.q.put(('error', '目标窗口没能回到前台'))
        else:
            if not self.popup.visible:
                self.popup.show(140, 140)
            self.do_grab()
    def service_label(self) -> str:
        return self.translator.service_label()
    def hotkey_label(self) -> str:
        st = self.hotkey_status
        if not st:
            return '热键：未初始化'
        else:
            return self.hotkeys.summary()
    def model_label(self) -> str:
        return self.translator._model or '未探测'
    def quit(self):
        self.paused = True
        try:
            self.hotkeys.shutdown()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)
def build_root() -> tk.Tk:
    """建根窗口（隐藏）与主循环分开，界面代码才可能被自动化测试驱动。"""
    root = tk.Tk()
    root.withdraw()
    root.title('ImeBridge')
    return root
def main():
    if not single_instance():
        return
    else:
        cfg = load_config()
        root = build_root()
        Bridge(root, cfg)
        root.mainloop()
if __name__ == '__main__':
    main()