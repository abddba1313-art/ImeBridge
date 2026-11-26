# -*- coding: utf-8 -*-
"""开机自启：HKCU\\...\\Run"""
import os
import sys
import winreg

RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
VALUE = 'ImeBridge'

def exe_command() -> str:
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    here = os.path.abspath(os.path.join(os.path.dirname(__file__), 'main.py'))
    return f'"{sys.executable}" "{here}"'

def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            v, _ = winreg.QueryValueEx(k, VALUE)
            return bool(v)
    except Exception:
        return False

def current_command() -> str:
    """注册表里现在存着的启动命令；没开过就是空串。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            v, _ = winreg.QueryValueEx(k, VALUE)
            return str(v or '')
    except Exception:
        return ''

def points_to_self() -> bool:
    """自启项是否指向当前这个 exe / 脚本。

    存的是**绝对路径**，所以 exe 一改名或挪位置它就悄悄失效了 —— 而 is_enabled()
    照样返回 True，光看"开没开"永远发现不了。
    """
    return current_command() == exe_command()

def enable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, exe_command())
        return True
    except Exception:
        return False

def disable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, VALUE)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False
