# 输入翻译桥 ImeBridge

> 把任意输入框变成翻译器：打字实时出译文、划词自动翻译、一键写回原文替换。
> **单个 exe + 一个 GGUF 模型文件，完全离线，不需要 Ollama / LM Studio / Python。**

[English](#english) · [中文](#chinese)

---

<a name="chinese"></a>
## 这是什么

一个 Windows 后台小工具（托盘常驻，当前源码构建约 35 MB 单文件）。它在任意程序（微信、QQ、浏览器、Word、记事本、聊天框…）里：

| 功能 | 怎么用 |
|---|---|
| **输入实时翻译** | 光标放进输入框开始打字，旁边弹出不抢焦点的小窗，逐字刷新译文 |
| **写回 / 撤销** | 一键把译文替换掉刚输入的原文，可撤销恢复 |
| **划词翻译** | 在网页/QQNT/Word 里直接选中文字，约 0.3 秒自动弹译文悬浮窗 |
| **抓屏翻译** | 微信这类零无障碍的自绘程序，按一个热键复制你划好的选区来翻（读完自动还原剪贴板） |
| **双语方向** | 划词窗自带「源语言 → 目标语言」双选框，与镜像小窗方向互相独立 |

翻译引擎默认是本机跑的 **腾讯 Hy-MT2 / Hy-MT3-1.8B GGUF**（经 llama.cpp `llama-server`），
也支持接入任意 **OpenAI 兼容云端 API**（设置里填地址 + Key 即可，Key 用 Windows DPAPI 加密落盘）。
源码保留了旧版 NLLB 路由代码以保持与 12.0 EXE 的二进制行为一致，但当前发布包不再附带
NLLB 旁路服务，配置文件中也已移除相关启动项；实际翻译由主模型或云端 API 完成。

## 和同类项目的差别

GitHub 上的翻译悬浮工具几乎都要求你**先装好 Ollama/LM Studio 并拉好模型**。
本项目的定位是 **out-of-the-box offline**：把 `llama-server.exe` + `Hy-MT2-1.8B-Q8_0.gguf`（≈2 GB）
和本工具放在同一个文件夹，双击启动 bat，模型服务与翻译桥一次拉起，
剩下的和装完一个普通 Windows 软件没有区别。没有 Docker、没有 API 账户、没有任何请求出机器。

## 快速开始（用发布产物）

**方式 A · 安装包（推荐，中文）**
1. 到 [Releases](../../releases) 下载 `ImeBridge-12.0-setup.exe`（约 71 MB），双击安装到
   `D:\llama-b11541-bin-win-cpu-x64`（路径可改）——一次装齐：llama.cpp b11541 CPU 运行时
   + `翻译start_translation_service.bat` + `输入翻译桥 12.0.exe`（安装时自动校验 MD5 与 360 白名单一致；新机器自动预置服务端口 1236，已有配置不动）
2. 下载 `Hy-MT3-1.8B-Q8_0.gguf` 放进该目录
   （ModelScope：[Tencent-Hunyuan/Hy-MT3-1.8B-GGUF](https://modelscope.cn/models/Tencent-Hunyuan/Hy-MT3-1.8B-GGUF)，或 HF tencent/Hy-MT3-1.8B-GGUF）
3. 双击 `翻译start_translation_service.bat`，模型选 `[2]`（Q8_0）——服务就绪后自动拉起托盘翻译桥
4. 光标进任意输入框打字。首次启动 SmartScreen 拦截：「更多信息 → 仍要运行」（未做代码签名，见下文）

**方式 B · 绿色压缩包（英文启动器）**
1. 下载 `ImeBridge-12.0-win64.zip` 解压到任意文件夹，把模型 gguf 放入同一文件夹
2. 双击 `start_translation_service.bat`（选择 Q4_K_M / Q8_0 / Q2_K，监听 1236 后启动 `*12.0.exe`）

默认热键（可改，冲突时自动降级到空闲键并在托盘/设置里告知）：

| 热键 | 作用 |
|---|---|
| `Ctrl+Alt+Shift+T` | 立即翻译当前输入 |
| `Ctrl+Alt+Shift+B` | 显示 / 隐藏小窗 |
| `Ctrl+Alt+Shift+Y` | 用译文替换原文 |
| `Ctrl+Alt+Shift+Z` | 撤销替换，恢复原文 |
| `Ctrl+Alt+Shift+D` | 划词强制翻译（自绘程序降级通道） |

## 从源码运行 / 构建

```bash
# 源码运行（需要 Python 3.12 + tkinter）
pip install -r requirements-build.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python src/main.py

# 打成单文件 exe（PyInstaller，产物在 dist/）
python build_exe.py
```

> 为与 12.0 EXE 完全一致，源码里的默认 `api_base` 仍是 `127.0.0.1:1235`；随包启动器监听
> `1236`。直接源码运行且没有现有配置时，请在设置里把端口改成 `1236`，或使用发布包已有的配置。

`launcher/start_translation_service.bat` 是随包分发的启动器：提供 Hy-MT3 三档模型选择，
自动探测目录里的 llama-server，监听 1236，并启动目录内的 `*12.0.exe`。

## 已知边界（实测结论，不吹牛）

- **1.8B 小模型的能力边界**：英/日/韩/俄/葡/法等高资源语言很稳；哈萨克/吉尔吉斯/乌兹别克
  这类低资源语言在小模型上会复读/漂语种——这不是本工具的 bug，是模型没学过。
  解法：换更大的模型，或切云端大模型 API。
- **划词通道能力差异**：UIA 暴露选区的程序（浏览器、Electron、QQNT、Office、记事本）走非入侵读取；
  微信 4.x / 旧 QQ 这类自绘程序读不到，只能热键降级为「Ctrl+C → 读剪贴板 → 还原」，一个按键都不会多发。
- Chromium/Electron 默认不开网页无障碍树，本工具会主动「踢醒」它（oleacc），个别版本首弹会慢半拍。
- 未做代码签名：新下载的首次运行会有 SmartScreen 提示；部分杀软对 PyInstaller 单文件 exe 有误报史，
  源码全公开 + 自行构建可完全规避。
- 旧版 NLLB 路由代码仍保留在源码中用于二进制兼容；当前发布包不再附带 NLLB 服务或模型。
  Hy-MT2/3 GGUF 遵循腾讯社区许可证。

## 隐私

默认配置下 **没有任何数据出机器**。只有两种例外，且都需要你主动配置：
在设置里填了云端 API 地址，或手动打开了联网选项。日志只写在
`%APPDATA%\ImeBridge\bridge.log`，配置里的 API Key 以 DPAPI 密文存储（换机器/换用户解不开）。

## License

MIT © 2026 Xianglong Han. 附带模型文件遵循各自的许可证（见上文）。

## 源码来源说明（provenance）

本仓库源码由作者本人从自己发布的二进制（`输入翻译桥 12.0.exe`，PyInstaller 解包 +
Python 3.12 字节码反编译）逐模块重建而来——原始工作区在一次磁盘清理中被丢失。
每个模块都经过 `dis` 反汇编逐函数比对修正；行为与本仓库对应的发布版 exe 一致。
2026-11-26 复核：补齐 `word_bridge.py`，锁定正式 EXE 内嵌的依赖版本；对同一段 736 字选区，
正式版与新构建均发出完全相同的 7 个分块翻译请求，划词窗口截图逐像素一致。
历史版本号（v2.3 → v2.8.2 的内部演进记录仍留在代码注释里）对应对外版本 1.x–12.0。

---

<a name="english"></a>
## English

**ImeBridge turns any text field into a translator.** A ~35 MB single-file Windows tray app
that translates while you type (floating non-focus-stealing popup), translates text you select
in browsers / Office / chat apps, and can replace your original input with the translation —
with one-key undo.

Out of the box, fully offline: put `llama-server.exe` + `Hy-MT2-1.8B-Q8_0.gguf` next to the app,
double-click one `.bat`. No Ollama, no LM Studio, no Python, no account, nothing leaves your
machine. (Optionally point it at any OpenAI-compatible cloud API instead; the API key is
stored DPAPI-encrypted.)

Highlights:

- **Legacy routing compatibility** — old NLLB routing code remains for binary fidelity, but the
  current package no longer ships or starts an NLLB sidecar.
- **Selection translation** with two independent direction pickers (source → target), decoupled
  from the mirror window's language.
- **Non-invasive input detection** via UI Automation + a clipboard-guarded fallback (Ctrl+C only,
  clipboard restored in ~1.2 s) for apps that expose nothing (WeChat 4.x, legacy QQ).
- 5 configurable hotkeys with automatic downgrade to free key combos on conflict, and visible
  status in tray + popup + log.
- Built-in long-text chunking, loop-repeat collapse, cloud API differences handling
  (`max_tokens`-less 400-retry), and per-field DPAPI-encrypted secrets.

Known limits (measured, not marketing): the bundled 1.8B model is genuinely weak on
Kazakh/Kyrgyz/Uzbek — use a larger model or a cloud model for those. Unsigned binaries
trigger SmartScreen on first run; antivirus may false-positive on PyInstaller exes — build
from source to be safe.

MIT licensed. Models carry their own licenses (Tencent Hy-MT community license).
