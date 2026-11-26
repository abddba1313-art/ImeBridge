# -*- coding: utf-8 -*-
"""Word / WPS 精细替换
优先级：COM 对象模型（Word.Application / Kwps.Application）
  - 段落级替换，排除段落标记（不合并段落）
  - 替换后把选区恢复到「译文末尾」，光标不丢
  - 撤销走 Word 原生撤销栈 Application.Undo()，并逐次校验段落文本是否回到原中文
兜底：UIA TextPattern（Select + Delete + 粘贴），同样排除段落标记，粘贴后重设光标
"""
import time

PROGIDS = {
    'winword.exe': ['Word.Application'],
    'wps.exe': ['Kwps.Application', 'wps.Application', 'Word.Application'],
    'wordpad.exe': [],
}
EXPAND_PARAGRAPH = 4
EP_END, SRC_END = (1, 2)


def _co(fn, *a, **kw):
    import pythoncom
    pythoncom.CoInitialize()
    try:
        return fn(*a, **kw)
    except Exception:
        return None
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            raise


def _attach(proc: str):
    ids = PROGIDS.get(proc)
    if not ids:
        return None, None
    import win32com.client
    for pid in ids:
        try:
            app = win32com.client.GetActiveObject(pid)
        except Exception:
            continue
        try:
            if app and app.Documents.Count > 0:
                return app, pid
        except Exception:
            continue
    return None, None


def _doc_for(app, title: str):
    """按窗口标题匹配文档，避免多文档时改错地方"""
    try:
        n = app.Documents.Count
        for i in range(1, n + 1):
            d = app.Documents(i)
            base = str(d.Name).rsplit('.', 1)[0].strip()
            if base and base in title:
                return d
    except Exception:
        pass
    try:
        return app.ActiveDocument
    except Exception:
        return None


def _selection(doc):
    try:
        return doc.ActiveWindow.Selection
    except Exception:
        return doc.Application.Selection


def _paragraph_bounds(sel):
    """返回 (para_start, para_end_safe, para_text) —— end 已排除段落标记"""
    ps = pe = None
    try:
        p = sel.Paragraphs(1)
        ps, pe = int(p.Start), int(p.End)
    except Exception:
        ps, pe = int(sel.Start), int(sel.End)
    safe = pe - 1 if pe is not None and pe > ps else pe
    doc = sel.Document
    txt = doc.Range(ps, safe).Text
    return ps, safe, txt


def snapshot(hwnd, proc, title):
    def run():
        app, pid = _attach(proc)
        if not app:
            return None
        doc = _doc_for(app, title)
        if doc is None:
            return None
        sel = _selection(doc)
        ps, pe, ptxt = _paragraph_bounds(sel)
        return {
            'mode': 'com',
            'progid': pid,
            'doc': str(doc.Name),
            'para_start': ps,
            'para_end': pe,
            'para_text': ptxt,
            'sel_start': int(sel.Start),
            'sel_end': int(sel.End),
            'undo_depth': int(app.UndoCount) if _has_undo(app) else 0,
        }
    try:
        return _co(run)
    except Exception:
        return None


def _has_undo(app):
    try:
        _ = app.UndoCount
        return True
    except Exception:
        return False


def replace_paragraph(hwnd, proc, title, text, snap):
    def run():
        app, _ = _attach(proc)
        if not app:
            return False, 'COM 未连接，改用 UIA 兜底', None
        doc = _doc_for(app, title)
        if doc is None:
            return False, '找不到目标文档', None
        sel = _selection(doc)
        ps, pe, ptxt = _paragraph_bounds(sel)
        new_snap = {
            'mode': 'com',
            'progid': snap.get('progid') if snap else None,
            'doc': str(doc.Name),
            'para_start': ps,
            'para_end': pe,
            'para_text': ptxt,
            'sel_start': int(sel.Start),
            'sel_end': int(sel.End),
            'undo_depth': int(app.UndoCount) if _has_undo(app) else 0,
        }
        rng = doc.Range(ps, pe)
        rng.Text = text
        caret = ps + len(text)
        try:
            sel.SetRange(caret, caret)
            sel.ScrollIntoView(0)
        except Exception:
            pass
        new_snap['new_end'] = caret
        return True, '已替换当前段落（可撤销）', new_snap
    try:
        return _co(run)
    except Exception as e:
        return False, f'COM 替换异常：{e}', None


def undo_last(hwnd, proc, title, snap, original):
    def run():
        app, _ = _attach(proc)
        if not app:
            return False, 'COM 未连接'
        doc = _doc_for(app, title)
        if doc is None:
            return False, '找不到目标文档'
        sel = _selection(doc)
        base = (original or '').strip()
        for i in range(1, 4):
            try:
                app.Undo()
            except Exception:
                return False, '撤销栈不可用'
            time.sleep(0.18)
            try:
                _, _, ptxt = _paragraph_bounds(sel)
            except Exception:
                ptxt = ''
            if not base:
                continue
            if ptxt.strip() == base.strip():
                try:
                    sel.SetRange(int(snap.get('sel_start', 0)), int(snap.get('sel_end', 0)))
                except Exception:
                    pass
                return True, f'已撤销（第 {i} 次撤销命中原文）'
        return False, '撤销未回到原文，已改用直接写回'
    try:
        return _co(run)
    except Exception as e:
        return False, f'撤销异常：{e}'


def restore_original(hwnd, proc, title, snap, original):
    def run():
        app, _ = _attach(proc)
        if not app:
            return False, 'COM 未连接'
        doc = _doc_for(app, title)
        if doc is None:
            return False, '找不到目标文档'
        sel = _selection(doc)
        ps, pe, _ = _paragraph_bounds(sel)
        doc.Range(ps, pe).Text = original
        try:
            sel.SetRange(ps, ps + len(original))
            sel.ScrollIntoView(0)
        except Exception:
            pass
        return True, '已写回中文原文'
    try:
        return _co(run)
    except Exception as e:
        return False, f'写回异常：{e}'


def current_paragraph_text(proc, title):
    def run():
        app, _ = _attach(proc)
        if not app:
            return None
        doc = _doc_for(app, title)
        if doc is None:
            return None
        try:
            _, _, t = _paragraph_bounds(_selection(doc))
            return t
        except Exception:
            return None
    try:
        return _co(run)
    except Exception:
        return None
