# -*- coding: utf-8 -*-
"""v2.6 双引擎的纯逻辑层：中文语种名 ↔ FLORES-200 语言码，以及桥→NLLB 服务的报文协议。

为什么要有这个文件：llama.cpp 官方不支持 NLLB 架构（PR #18359 未合并，
实测 b11541 的 dll 里连 'nllb' 字样都没有），所以 NLLB 只能以**独立服务**
形态存在；而桥与它之间走 OpenAI 兼容通道，但中文提示词模板对 NLLB 这种
编码器-解码器模型毫无意义——它只认语言码。于是约定：命中 NLLB 路由的请求，
messages 内容换成机器可读的三行协议：

    LANG_IN:zho_Hans
    LANG_OUT:uzn_Latn
    <原文（可含换行，取剩余全部）>

本模块不 import ctranslate2 / 任何三方库，桥和测试在任何环境都能导入。
"""
import re

FLORES = {
    '中文': 'zho_Hans', '英文': 'eng_Latn', '日文': 'jpn_Jpan', '韩文': 'kor_Hang',
    '法文': 'fra_Frnc', '德文': 'deu_Latn', '西班牙文': 'spa_Latn', '俄文': 'rus_Cyrl',
    '葡萄牙文': 'por_Latn', '吉尔吉斯文': 'kir_Cyrl', '哈萨克文': 'kaz_Cyrl',
    '乌兹别克文': 'uzn_Latn', '维吾尔文': 'uig_Arab', '越南文': 'vie_Latn',
    '泰文': 'tha_Thai', '印尼文': 'ind_Latn', '意大利文': 'ita_Latn',
    '阿拉伯文': 'arb_Arab', '土耳其文': 'tur_Latn', '印地文': 'hin_Deva',
    '马来文': 'zsm_Latn', '波兰文': 'pol_Latn', '荷兰文': 'nld_Latn',
    '乌克兰文': 'ukr_Cyrl', '世界语': 'epo_Latn',
}
# Hy-MT3 书写系统级语言名（config.py 迁移后的新名）
FLORES.update({
    '西里尔哈萨克语': 'kaz_Cyrl',
    '吉尔吉斯语': 'kir_Cyrl',
    '乌兹别克语': 'uzn_Latn',
})

_CODE_RE = re.compile('^[a-z]{3}_[A-Za-z]{4}$')
LANG_IN = 'LANG_IN:'
LANG_OUT = 'LANG_OUT:'


def flores_code(name: str):
    """中文语种名 → FLORES 码；不认识返回 None（= 该语种留在主模型）。"""
    return FLORES.get((name or '').strip())


def is_code(s: str) -> bool:
    return bool(_CODE_RE.match(s or ''))


def build_request(text: str, in_code: str, out_code: str) -> str:
    """三行协议报文。text 里的换行原样保留（解析端按'前两行是协议'切）。"""
    return '%s%s\n%s%s\n%s' % (LANG_IN, in_code, LANG_OUT, out_code, text)


def parse_request(content: str):
    """解析协议 → (in_code, out_code, text)。不合式抛 ValueError。"""
    lines = (content or '').split('\n')
    if len(lines) < 3:
        raise ValueError('NLLB 协议报文不足三行（LANG_IN/LANG_OUT/正文）')
    a, b = lines[0], lines[1]
    if not a.startswith(LANG_IN) or not b.startswith(LANG_OUT):
        raise ValueError('NLLB 协议报文前两行必须是 LANG_IN:<码> 与 LANG_OUT:<码>')
    ic, oc = a[len(LANG_IN):].strip(), b[len(LANG_OUT):].strip()
    if not is_code(ic) or not is_code(oc):
        raise ValueError('NLLB 语言码不合式（要 zho_Hans 这样的三位字母_四位字母）')
    return ic, oc, '\n'.join(lines[2:])
