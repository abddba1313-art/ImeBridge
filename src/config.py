# -*- coding: utf-8 -*-
"""配置：%APPDATA%\\ImeBridge\\config.json

v2.3 变化：
- 支持**云端** OpenAI 兼容服务：api_base 可填 https 地址，新增 api_key；
  Key 落盘时用 DPAPI 加密（见 secret.py），配置文件里不再有明文 Key。
- 热键默认值换成本机实测空闲的组合（ctrl+alt+t 那批在本机全被别的程序占了）。
- 配置项是给**设置窗口**用的，用户不需要也不应该去手改这个 json。

Hy-MT3 语言迁移：哈萨克/吉尔吉斯/乌兹别克按书写系统拆分语言名
（阿拉伯字母哈萨克语 / 西里尔哈萨克语 / 吉尔吉斯语 / 乌兹别克语），
老配置加载时自动迁移（见 merge_new_languages / load_config），迁移即落盘。
"""
import json
import os
from dataclasses import asdict, dataclass

import secret

APP_NAME = 'ImeBridge'

# 旧语言名 → 书写系统级新语言名
_LANGUAGE_ALIASES = {
    '哈萨克文': ('阿拉伯字母哈萨克语', '西里尔哈萨克语'),
    '哈萨克语': ('阿拉伯字母哈萨克语', '西里尔哈萨克语'),
    '吉尔吉斯文': ('吉尔吉斯语',),
    '乌兹别克文': ('乌兹别克语',),
}
# 单选字段（source/target）用的单一映射
_SINGLE_LANGUAGE_ALIASES = {
    '哈萨克文': '西里尔哈萨克语',
    '哈萨克语': '西里尔哈萨克语',
    '吉尔吉斯文': '吉尔吉斯语',
    '乌兹别克文': '乌兹别克语',
}
# 这些语言不走本地 NLLB 副引擎（Hy-MT3 主模型直接覆盖）
_NLLB_DISABLED_LANGUAGES = {
    '哈萨克文', '哈萨克语', '阿拉伯字母哈萨克语', '西里尔哈萨克语',
    '吉尔吉斯文', '吉尔吉斯语', '乌兹别克文', '乌兹别克语',
}

V25_NEW_LANGUAGES = ('葡萄牙文', '吉尔吉斯语', '阿拉伯字母哈萨克语', '西里尔哈萨克语', '乌兹别克语', '维吾尔文')
DEFAULT_LANGUAGES = ('英文', '日文', '韩文', '法文', '德文', '西班牙文', '俄文', '葡萄牙文',
                     '吉尔吉斯语', '阿拉伯字母哈萨克语', '西里尔哈萨克语', '乌兹别克语', '维吾尔文', '中文')


def config_dir() -> str:
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.join(config_dir(), 'config.json')


def log_path() -> str:
    return os.path.join(config_dir(), 'bridge.log')


def merge_new_languages(langs) -> list:
    """v2.5 迁移：老配置的语言列表缺了新增语言时**只追加缺的，不删不重排**；
    旧语言名按书写系统展开成新名。用户自己加过/删过的语言一律保留原顺序。"""
    out = []
    for value in list(langs or []):
        name = str(value).strip()
        if not name:
            continue
        for item in _LANGUAGE_ALIASES.get(name, (name,)):
            if item not in out:
                out.append(item)
    for name in V25_NEW_LANGUAGES:
        if name not in out:
            out.append(name)
    return out


@dataclass
class Config:
    api_base: str = 'http://127.0.0.1:1235/v1'
    model: str = ''
    model_hint: str = 'mt,hy,hunyuan'
    api_key: str = ''
    api_key_enc: str = ''
    temperature: float = 0.0
    max_tokens: int = 2048
    request_timeout: int = 120
    health_interval_s: int = 30
    api_presets: list = None
    source_lang: str = '中文'
    target_lang: str = '英文'
    languages: list = None
    max_chars: int = 300
    chunk_size: int = 120
    prompt_template: str = '你是专业翻译引擎。把下面的{source}翻译成{target}。要求：只输出译文；保留原文的换行；不要解释、不要引号、不要前后缀。\n\n{source_text}'
    poll_fast_ms: int = 60
    poll_slow_ms: int = 250
    idle_ms: int = 1200
    follow_caret: bool = True
    caret_follow_px: int = 8
    popup_width: int = 420
    popup_height: int = 300
    auto_show: bool = True
    topmost: bool = True
    hotkey_translate: str = 'ctrl+alt+shift+t'
    hotkey_toggle: str = 'ctrl+alt+shift+b'
    hotkey_replace: str = 'ctrl+alt+shift+y'
    hotkey_undo: str = 'ctrl+alt+shift+z'
    hotkey_extra_fallbacks: str = 'ctrl+alt+f9;ctrl+alt+j;ctrl+alt+m'
    hotkey_selection: str = 'ctrl+alt+shift+d'
    nllb_base: str = 'http://127.0.0.1:1237/v1'
    nllb_langs: list = None
    nllb_polish: bool = True
    sel_watch: bool = True
    sel_poll_ms: int = 450
    sel_min_chars: int = 1
    sel_max_chars: int = 1000
    sel_win_w: int = 480
    sel_win_h: int = 320
    sel_source_lang: str = '中文'
    sel_target_lang: str = '英文'
    sel_link_langs: bool = False
    mirror_password: bool = False
    autostart: bool = True
    log_level: str = 'INFO'
    auto_retranslate: bool = True
    retranslate_min_chars: int = 2
    word_use_com: bool = True
    word_verify_undo: bool = True
    history_size: int = 10
    kick_accessibility: bool = True
    blind_apps: list = None
    blind_auto_grab: bool = True

    def __post_init__(self):
        if self.languages is None:
            self.languages = list(DEFAULT_LANGUAGES)
        else:
            self.languages = merge_new_languages(self.languages)
        if self.blind_apps is None:
            self.blind_apps = ['weixin.exe', 'wechat.exe']
        if self.nllb_langs is None:
            self.nllb_langs = ['乌兹别克文', '吉尔吉斯文', '哈萨克文']
        if self.api_presets is None:
            self.api_presets = ['http://127.0.0.1:1235/v1', 'http://127.0.0.1:8000/v1',
                                'https://api.openai.com/v1', 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                                'https://api.deepseek.com/v1', 'https://open.bigmodel.cn/api/paas/v4']
        # Hy-MT3：这些语言由主模型直翻，NLLB 副引擎名单里一律剔除
        self.nllb_langs = [
            str(name).strip()
            for name in (self.nllb_langs or [])
            if str(name).strip() not in _NLLB_DISABLED_LANGUAGES
        ]

    def is_cloud(self) -> bool:
        b = (self.api_base or '').lower()
        return not (b.startswith('http://127.') or b.startswith('http://localhost') or b.startswith('http://[::1]'))


def _migrate_plain_key(data: dict) -> str:
    """老配置里可能有明文 api_key：取出来用一次，下次保存就变成密文。"""
    plain = (data.get('api_key') or '').strip()
    if plain:
        return plain
    enc = (data.get('api_key_enc') or '').strip()
    if enc:
        return secret.unprotect(enc)
    return ''


def load_config() -> Config:
    cfg = Config()
    p = config_path()
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            skip = {'api_key', 'api_key_enc'}
            cfg.__dict__.update({k: v for k, v in data.items() if k in cfg.__dict__ and k not in skip})
            cfg.api_key = _migrate_plain_key(data)
            cfg.languages = merge_new_languages(cfg.languages or [])
            if data.get('sel_max_chars') == 500:
                cfg.sel_max_chars = 1000
            if 'sel_source_lang' not in data:
                cfg.sel_source_lang = cfg.source_lang or '中文'
                cfg.sel_target_lang = cfg.target_lang or '英文'
            if 'sel_link_langs' not in data:
                cfg.sel_link_langs = False
        except Exception:
            pass
    else:
        save_config(cfg)
        return cfg
    # Hy-MT3 迁移：单选语言字段规范化 + NLLB 名单剔除，变了就落盘
    before = (cfg.source_lang, cfg.target_lang, cfg.sel_source_lang, cfg.sel_target_lang, list(cfg.nllb_langs or []))
    for field in ('source_lang', 'target_lang', 'sel_source_lang', 'sel_target_lang'):
        value = str(getattr(cfg, field, '') or '').strip()
        setattr(cfg, field, _SINGLE_LANGUAGE_ALIASES.get(value, value))
    cfg.nllb_langs = [
        str(name).strip()
        for name in (cfg.nllb_langs or [])
        if str(name).strip() not in _NLLB_DISABLED_LANGUAGES
    ]
    after = (cfg.source_lang, cfg.target_lang, cfg.sel_source_lang, cfg.sel_target_lang, list(cfg.nllb_langs or []))
    if after != before:
        save_config(cfg)
    return cfg


def save_config(cfg: Config) -> None:
    """落盘。api_key 明文**绝不**写进文件，只写 DPAPI 密文。"""
    try:
        d = asdict(cfg)
        key = (cfg.api_key or '').strip()
        d.pop('api_key', None)
        try:
            d['api_key_enc'] = secret.protect(key) if key else ''
        except Exception:
            # DPAPI 不可用时的降级：宁可写明文也不能丢用户的 Key
            d['api_key_enc'] = ''
            d['api_key'] = key
        with open(config_path(), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
