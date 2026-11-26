# -*- coding: utf-8 -*-
"""托盘常驻：设置入口、抓取入口、热键状态都要在这里看得见"""
import threading


def _icon_image():
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([1, 1, 31, 31], radius=7, fill=(43, 92, 214, 255))
    try:
        f = ImageFont.truetype('arial.ttf', 19)
    except Exception:
        f = ImageFont.load_default()
    d.text((16, 16), '译', fill=(255, 255, 255, 255), font=f, anchor='mm')
    return img


def start_tray(bridge):
    try:
        import pystray
        from pystray import MenuItem as Item
    except Exception:
        return None
    menu = pystray.Menu(
        Item('显示 / 隐藏小窗', lambda: bridge.toggle()),
        Item('抓取并翻译（微信等）', lambda: bridge.grab_from_tray()),
        Item('划词翻译（选中文字后点这里）', lambda: bridge.sel_from_tray()),
        pystray.Menu.SEPARATOR,
        Item('设置…（服务地址 / API Key / 热键）', lambda: bridge.open_settings()),
        pystray.Menu.SEPARATOR,
        Item(lambda: bridge.service_label(), None, enabled=False),
        Item(lambda: f'当前模型：{bridge.model_label()}', None, enabled=False),
        Item(lambda: bridge.hotkey_label(), None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item('跟随光标逐字刷新', lambda: bridge.toggle_follow(), checked=lambda: bridge.cfg.follow_caret),
        Item('选语言后自动重译', lambda: bridge.toggle_auto(), checked=lambda: bridge.cfg.auto_retranslate),
        Item('暂停监听', lambda: bridge.toggle_pause(), checked=lambda: bridge.paused),
        Item('开机自启', lambda: bridge.toggle_autostart(), checked=lambda: bridge.autostart_enabled()),
        pystray.Menu.SEPARATOR,
        Item('打开设置窗口', lambda: bridge.open_settings()),
        Item('打开 config.json（高级）', lambda: bridge.open_config_json()),
        Item('打开配置/日志目录', lambda: bridge.open_log_dir()),
        Item('测试翻译', lambda: bridge.test_translate()),
        pystray.Menu.SEPARATOR,
        Item('退出', lambda: bridge.quit()),
    )
    icon = pystray.Icon('ImeBridge', _icon_image(), '输入翻译桥 · 翻译助手', menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon
