# -*- coding: utf-8 -*-
"""PyInstaller 单文件打包：python build_exe.py [版本后缀]

产物 dist/ImeBridge.exe（无控制台窗口）。国内网络建议：
  pip install -r requirements-build.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
ENTRY = SRC / 'main.py'
NAME = 'ImeBridge'

args = [
    sys.executable, '-m', 'PyInstaller',
    '--onefile', '--windowed', '--clean', '--noconfirm',
    '--name', NAME,
    '--paths', str(SRC),
    # 运行时按名字找模块（from popup import Popup），src 整体加 paths 即可；
    # comtypes 生成缓存目录在只读介质会报错，main 里已兜底，这里再显式收编
    '--hidden-import', 'uiautomation',
    '--hidden-import', 'win32clipboard',
    '--hidden-import', 'win32gui',
    '--hidden-import', 'win32con',
    '--hidden-import', 'comtypes.stream',
    '--exclude-module', 'tkinter.test',
    str(ENTRY),
]

if __name__ == '__main__':
    print('RUN:', ' '.join(args))
    rc = subprocess.call(args, cwd=str(ROOT))
    exe = ROOT / 'dist' / (NAME + '.exe')
    if rc == 0 and exe.exists():
        print('OK ->', exe, exe.stat().st_size, 'bytes')
    else:
        print('BUILD FAILED rc=%s' % rc)
        sys.exit(rc or 1)
