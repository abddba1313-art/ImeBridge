# -*- coding: utf-8 -*-
"""输入翻译桥 12.0 Windows 安装包（tkinter GUI，单 exe）。

双击后把 llama.cpp CPU 运行时 + 启动器 bat + 输入翻译桥 12.0.exe 共 53 个文件
解压到目标目录（默认 D:\\llama-b11541-bin-win-cpu-x64）。
模型 Hy-MT3-1.8B-Q8_0.gguf 不在包内（体积与许可），装完界面里给下载指引。

命令行（自检/无人值守用）：
    installer.exe --target <目录> --overwrite --quiet
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import zipfile

APP_TITLE = '输入翻译桥 12.0 · 安装'
DEFAULT_DIR = r'D:\llama-b11541-bin-win-cpu-x64'
BRIDGE_MD5 = '5004591f08bd7407392f97dd5f4b5f57'  # 与 360 白名单条目同一内容


def seed_config() -> str:
    """新机器没有 config.json 时预置 api_base=1236（与启动器 bat 监听的端口一致）。
    已存在配置一律不动——那是用户的设置，不是安装器的资产。"""
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'ImeBridge')
    p = os.path.join(d, 'config.json')
    if os.path.exists(p):
        return '保留现有配置'
    try:
        os.makedirs(d, exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'api_base': 'http://127.0.0.1:1236/v1'}, f, ensure_ascii=False, indent=2)
        return '已预置服务端口 1236'
    except Exception as e:
        return '配置预置失败（%s），首次运行请在设置里把端口改为 1236' % e


def payload_zip() -> str:
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'payload.zip')


def extract(target: str, overwrite: bool, report) -> tuple:
    """解压 payload 到 target。返回 (文件数, 总字节)。report(msg, done, total) 回调。"""
    zp = payload_zip()
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        total = sum(z.getinfo(n).file_size for n in names)
        done = 0
        for n in names:
            dst = os.path.join(target, n)
            if not overwrite and os.path.exists(dst):
                done += z.getinfo(n).file_size
                report('跳过已存在：%s' % n, done, total)
                continue
            with z.open(n) as src, open(dst, 'wb') as out:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    out.write(buf)
                    done += len(buf)
            report('已安装：%s' % n, done, total)
    return len(names), total


def verify_bridge(target: str) -> bool:
    p = os.path.join(target, '输入翻译桥 12.0.exe')
    if not os.path.exists(p):
        return False
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest() == BRIDGE_MD5


def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry('560x420')
    root.resizable(False, False)

    tk.Label(root, text='输入翻译桥 12.0 安装程序', font=('Microsoft YaHei UI', 14, 'bold')).pack(pady=(18, 4))
    tk.Label(root, text='llama.cpp CPU 运行时 + 启动器 + 翻译桥，一次装齐（不含模型文件）',
             fg='#666', font=('Microsoft YaHei UI', 9)).pack()

    frm = tk.Frame(root)
    frm.pack(fill='x', padx=28, pady=(20, 6))
    tk.Label(frm, text='安装到：').pack(side='left')
    var = tk.StringVar(value=DEFAULT_DIR)
    tk.Entry(frm, textvariable=var, width=48).pack(side='left', fill='x', expand=True)
    tk.Button(frm, text='浏览…', command=lambda: (
        var.set(filedialog.askdirectory(initialdir=var.get() or 'D:\\', title='选择安装目录') or var.get())
    )).pack(side='left', padx=6)

    ow = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text='覆盖已存在的同名文件（默认跳过）', variable=ow,
                   font=('Microsoft YaHei UI', 9)).pack(pady=4)

    bar = ttk.Progressbar(root, length=500, mode='determinate')
    bar.pack(pady=(14, 4))
    status = tk.Label(root, text='就绪。点击「安装」开始。', fg='#666', font=('Microsoft YaHei UI', 9), wraplength=520)
    status.pack()

    def log(msg, done, total):
        root.after(0, lambda: (
            status.configure(text='%s  (%.1f / %.1f MB)' % (msg, done / 1e6, total / 1e6)),
            bar.configure(value=100.0 * done / max(1, total)),
        ))

    def finish():
        target = var.get().strip().strip('"')
        ok = verify_bridge(target)
        seed = seed_config()
        msg = '安装完成：%s\n\n翻译桥校验 MD5 %s\n%s' % (
            target, '通过（与 360 白名单同一内容）' if ok else '不匹配！请检查杀软是否拦截', seed)
        steps = ('\n\n下一步：\n1. 下载 Hy-MT3-1.8B-Q8_0.gguf 放进该目录\n'
                 '   （ModelScope: Tencent-Hunyuan/Hy-MT3-1.8B-GGUF）\n'
                 '2. 双击「翻译start_translation_service.bat」→ 选 [2] 开始使用')
        if messagebox.askyesno(APP_TITLE, msg + steps + '\n\n现在打开安装目录？'):
            subprocess.Popen(['explorer', target])

    def worker():
        try:
            n, _ = extract(var.get().strip().strip('"'), ow.get(), log)
            root.after(0, finish)
        except Exception as e:
            root.after(0, lambda: messagebox.showerror(APP_TITLE, '安装失败：%s' % e))

    def go():
        target = var.get().strip().strip('"')
        if not target:
            messagebox.showwarning(APP_TITLE, '请填写安装目录')
            return
        drive = os.path.splitdrive(target)[0]
        if drive and not os.path.isdir(drive + '\\'):
            messagebox.showwarning(APP_TITLE, '驱动器 %s 不存在' % drive)
            return
        btn.configure(state='disabled')
        threading.Thread(target=worker, daemon=True).start()

    btn = tk.Button(root, text='安  装', width=18, height=1, command=go,
                    bg='#2b5cd6', fg='white', font=('Microsoft YaHei UI', 11, 'bold'))
    btn.pack(pady=16)
    root.mainloop()


def main():
    args = sys.argv[1:]
    if '--target' in args:
        target = args[args.index('--target') + 1]
        ow = '--overwrite' in args
        n, total = extract(target, ow, lambda *a: None if '--quiet' in args else print(a[0]))
        print('files=%d bytes=%d bridge_md5=%s config=%s' % (n, total, verify_bridge(target), seed_config()))
        return
    run_gui()


if __name__ == '__main__':
    main()
