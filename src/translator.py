# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'translator.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""翻译客户端：OpenAI 兼容端点，本地 LM Studio（127.0.0.1:1235）或任意云端。\n\nv2.3 变化：\n- 支持 **API Key**：有 Key 就发 `Authorization: Bearer <Key>`，没有就不发这个头\n  （LM Studio 不认 Authorization，发了反而可能被拒）。\n- 401/403 给可操作提示：\"在设置窗口里填 API Key\"，不再是一句 HTTP 401。\n- 云端常见差异：有的服务不认 `max_tokens`/`temperature`，400 时换一份精简载荷重试。\n- >300 字分段翻译再拼接（沿用 v2.1）。\n"""
import re
import threading
import time
import requests
import nllb_lang
class TranslateError(Exception):
    pass
POLISH_ZH = '你是译后编辑引擎。下面给出{source}原文和机器初译的中文译文。请对照原文只修正初译的措辞、标点和语法，保持中文、保持原意，严禁添加原文中不出现的国家、人名、机构，只输出修正后的中文，不要解释。\n原文：{src}\n初译：{raw}'
SENT_SPLIT = re.compile('(?<=[。！？；?!;\\n])')
def split_chunks(text: str, max_len: int, overflow: int=0) -> list:
    """按标点切块，每块 <= max_len；无标点的超长句硬切。\n\n    v2.8.2：overflow 允许**单句**最多超限这么多字不劈开（路由方向用 150 →\n    300~450 字的整句保留）。实测 1.3B 把两词谓语 \"болып табылады\" 按 300\n    字劈开后初译丢了大使人名——整句超限劈半的代价比多 150 字更高。\n    打包逻辑不变（多句合并仍守 max_len），只有\"单句本身超限\"才享受溢出。\n    """
    parts = [p for p in SENT_SPLIT.split(text) if p and p.strip()]
    chunks, cur = ([], '')
    for p in parts:
        if cur and len(cur) + len(p) > max_len:
            chunks.append(cur)
            cur = p
        else:
            cur += p
        while len(cur) > max_len + overflow:
            cut = cur.rfind(' ', 0, max_len + 1)
            if cut < max_len // 2:
                cut = cur.rfind(',', 0, max_len + 1)
            if cut < max_len // 2:
                cut = cur.rfind('，', 0, max_len + 1)
            if cut < max_len // 2:
                cut = max_len
            chunks.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        chunks.append(cur)
    return chunks or ([text] if text.strip() else [])
class Translator:
    def __init__(self, cfg):
        self.cfg = cfg
        self.s = requests.Session()
        self._model = ''
        self._model_ts = 0.0
        self._online = False
        self._nllb_online = False
        self._lock = threading.Lock()
    def headers(self) -> dict:
        """有 Key 才发 Authorization。\n\n        LM Studio 的本地服务不需要也不认这个头（实测无 Key 直连可用），\n        所以\"空 Key 不发头\"是本地能跑的前提；云端反过来 —— 没 Key 必被拒。\n        """
        key = (self.cfg.api_key or '').strip()
        return {'Authorization': 'Bearer %s' % key} if key else {}
    def health(self):
        try:
            ids = self.list_models()
            self._online = True
            return (True, ids)
        except Exception as e:
            self._online = False
            return (False, f'{type(e).__name__}: {e}')
    @property
    def online(self) -> bool:
        return self._online
    def list_models(self):
        r = self.s.get(self.cfg.api_base.rstrip('/') + '/models', headers=self.headers(), timeout=8)
        if r.status_code in (401, 403):
            raise TranslateError(self._auth_hint(r.status_code))
        r.raise_for_status()
        data = r.json().get('data') or r.json().get('models') or []
        return [m.get('id') or m.get('name') for m in data if not isinstance(m, dict) or (m.get('id') or m.get('name'))]
    def resolve_model(self) -> str:
        if self.cfg.model:
            return self.cfg.model
        else:
            with self._lock:
                if self._model and time.time() - self._model_ts < 60:
                    return self._model
                else:
                    try:
                        ids = self.list_models()
                        hints = [h.strip().lower() for h in self.cfg.model_hint.split(',') if h.strip()]
                        pick = ''
                        for h in hints:
                            for i in ids:
                                if h in i.lower():
                                    pick = i
                                    break
                            if pick:
                                break
                        self._model = pick or (ids[0] if ids else '')
                    except Exception:
                        self._model = self._model or ''
                    self._model_ts = time.time()
                    return self._model
    @staticmethod
    def _auth_hint(code: int) -> str:
        return 'HTTP %d：鉴权被拒 —— 在设置窗口「翻译服务」里填 API Key（或确认 Key 没过期、没多余空格）。' % code
    def nllb_route(self, target: str, source: str):
        """命中旁路返回 (in_code, out_code)，否则 None（走主模型）。\n        三重闸门：服务地址非空 + 目标语在路由清单里 + 源/目标都能映射 FLORES 码。\n        任何一个不满足都静默回主模型——主模型再差也是原来的行为，不引入新故障面。"""
        base = (getattr(self.cfg, 'nllb_base', '') or '').strip()
        if not base:
            return
        else:
            langs = getattr(self.cfg, 'nllb_langs', None) or []
            if target not in langs:
                return
            else:
                ic = nllb_lang.flores_code(source)
                oc = nllb_lang.flores_code(target)
                if not ic or not oc:
                    return None
                else:
                    return (ic, oc)
    def polish_route(self, target: str, source: str):
        """v2.8「小语种→中文」两段链的资格闸门（与 nllb_route 互斥）：\n        开关打开 + 目标是中文 + 源语言在 NLLB 路由清单里 + 双语可映射。\n        命中后：初译走 NLLB（语义对），润色走主模型（中文是 Hy-MT2 的强项）。"""
        if not getattr(self.cfg, 'nllb_polish', False):
            return
        else:
            base = (getattr(self.cfg, 'nllb_base', '') or '').strip()
            if not base:
                return
            else:
                langs = getattr(self.cfg, 'nllb_langs', None) or []
                if target != '中文' or source not in langs:
                    return None
                else:
                    ic = nllb_lang.flores_code(source)
                    oc = nllb_lang.flores_code('中文')
                    if not ic or not oc:
                        return None
                    else:
                        return (ic, oc)
    def translate(self, text: str, target: str=None, source: str=None) -> str:
        text = (text or '').strip()
        if not text:
            return ''
        else:
            target = target or self.cfg.target_lang
            src_lang = source or self.cfg.source_lang or '中文'
            route = self.nllb_route(target, src_lang)
            polish = None if route else self.polish_route(target, src_lang)
            if route or polish:
                ic, oc = route or polish
                base = (getattr(self.cfg, 'nllb_base', '') or '').strip()
                url = base.rstrip('/') + '/chat/completions'
                payload = {'model': 'nllb-200', 'messages': [{'role': 'user', 'content': nllb_lang.build_request(text, ic, oc)}], 'stream': False}
                hdrs = {}
                hint = '连不上 NLLB 小语种服务 %s：请运行「NLLB翻译服务.exe」（主程序文件夹里）；不想用可在设置里把「NLLB 服务地址」留空（留空后路由语言会退回主模型的旧行为）' % url
            else:
                prompt = self.cfg.prompt_template.format(source=src_lang, target=target, source_text=text)
                payload = {'model': self.resolve_model() or 'local-model', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': self.cfg.temperature, 'max_tokens': self.cfg.max_tokens, 'stream': False}
                url = self.cfg.api_base.rstrip('/') + '/chat/completions'
                hdrs = self.headers()
                hint = f'连不上 {url}（本地服务看 LM Studio 的 Local Server 是否已启动、端口是否对得上；云端看网络与地址）'
            try:
                r = self.s.post(url, json=payload, headers=hdrs, timeout=self.cfg.request_timeout)
                if r.status_code == 400:
                    slim = {'model': payload['model'], 'messages': payload['messages']}
                    r2 = self.s.post(url, json=slim, headers=hdrs, timeout=self.cfg.request_timeout)
                    if r2.status_code < 400:
                        r = r2
            except requests.exceptions.ConnectionError as e:
                if not route and (not polish):
                        self._online = False
                raise TranslateError(hint) from e
            except requests.exceptions.Timeout as e:
                raise TranslateError('翻译超时，模型可能仍在加载') from e
            if r.status_code in (401, 403):
                if not route and (not polish):
                        self._online = False
                raise TranslateError(self._auth_hint(r.status_code))
            else:
                if r.status_code == 404:
                    raise TranslateError(f"HTTP 404：地址或模型名不对（{url}，模型「{payload['model']}」）")
                else:
                    if r.status_code >= 400:
                        raise TranslateError(f'HTTP {r.status_code}: {r.text[:200]}')
                    else:
                        if not route and (not polish):
                                self._online = True
                        out = self._clean(self._extract(r.json()))
                        if not out:
                            raise TranslateError('模型返回空内容（换模型试试，或在设置里调低 max_tokens）')
                        else:
                            if polish:
                                out = self._polish_zh(text, out, src_lang)
                            return out
    def _polish_zh(self, src_text: str, raw: str, src_lang: str) -> str:
        """润色失败（主模型掉线/报错/空返回）一律退回 NLLB 初译——\n        带半角标点的正确译文也远好于再来一次 Hy 直译塌方。"""
        prompt = POLISH_ZH.format(source=src_lang, src=src_text, raw=raw)
        payload = {'model': self.resolve_model() or 'local-model', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': self.cfg.temperature, 'max_tokens': self.cfg.max_tokens, 'stream': False}
        url = self.cfg.api_base.rstrip('/') + '/chat/completions'
        try:
            r = self.s.post(url, json=payload, headers=self.headers(), timeout=self.cfg.request_timeout)
            if r.status_code == 400:
                slim = {'model': payload['model'], 'messages': payload['messages']}
                r2 = self.s.post(url, json=slim, headers=self.headers(), timeout=self.cfg.request_timeout)
                if r2.status_code < 400:
                    r = r2
            if r.status_code >= 400:
                return raw
            else:
                out = self._clean(self._extract(r.json()))
                if out:
                    self._online = True
                return out or raw
        except Exception:
            return raw
    def translate_long(self, text: str, target: str, progress=None, source: str=None) -> str:
        text = (text or '').strip()
        max_len = max(40, self.cfg.chunk_size)
        overflow = 0
        tgt = target or self.cfg.target_lang
        src_lang = source or self.cfg.source_lang or '中文'
        if max_len < 300 and (self.nllb_route(tgt, src_lang) or self.polish_route(tgt, src_lang)):
                max_len, overflow = (300, 150)
        chunks = split_chunks(text, max_len, overflow)
        if len(chunks) == 1:
            if progress:
                progress('翻译中 1/1')
            return self.translate(chunks[0], target, source)
        else:
            outs = []
            for i, c in enumerate(chunks, 1):
                if progress:
                    progress(f'分段翻译 {i}/{len(chunks)}')
                outs.append(self.translate(c, target, source))
            if progress:
                progress(f'已拼接 {len(chunks)} 段')
            return ''.join(outs)
    def nllb_health(self):
        """探一次 NLLB 服务 /models。旁路禁用返回 None。"""
        base = (getattr(self.cfg, 'nllb_base', '') or '').strip()
        if not base:
            return
        else:
            try:
                r = self.s.get(base.rstrip('/') + '/models', timeout=6)
                self._nllb_online = r.status_code < 400
            except Exception:
                self._nllb_online = False
            return self._nllb_online
    def service_label(self) -> str:
        base = (self.cfg.api_base or '').rstrip('/')
        tag = '云端' if self.cfg.is_cloud() else '本地'
        state = '在线' if self._online else '离线'
        key = '已填 Key' if (self.cfg.api_key or '').strip() else '无 Key'
        out = f'服务：{state} {tag} {base}（{key}）'
        nb = (getattr(self.cfg, 'nllb_base', '') or '').strip()
        if nb:
            langs = getattr(self.cfg, 'nllb_langs', None) or []
            nst = '在线' if getattr(self, '_nllb_online', False) else '离线'
            out += f"｜小语种 {nst} {nb}（{','.join(langs)}）"
        return out
    @staticmethod
    def _extract(d: dict) -> str:
        try:
            ch = d['choices'][0]
            msg = ch.get('message') or {}
            if msg.get('content'):
                return msg['content']
            if ch.get('text'):
                return ch['text']
            return ''
        except Exception:
            return ''
    @staticmethod
    def _clean(s: str) -> str:
        s = (s or '').strip()
        s = re.sub('^```[a-zA-Z]*\\n?', '', s)
        s = re.sub('\\n?```$', '', s).strip()
        s = re.sub('^\\s*(译文|翻译|英文|英语|日文|韩文|English|Japanese|Translation|Output)\\s*[:：]\\s*', '', s, flags=re.I)
        s = Translator.collapse_repeats(s)
        return s.strip('“”\"\' \n')
    @staticmethod
    def collapse_repeats(s: str) -> str:
        """v2.5 循环复读防护：小模型翻低资源语言（实测哈萨克文）会整段卡进\n        「ٴاندارىن ٴاندارىن ٴاندارىن…」的死循环，把 max_tokens 全烧在复读上。\n        同一 4~40 字符片段连续出现 ≥3 次时截成一次，宁可少给也不能给一屏乱码。"""
        if not s:
            return s
        else:
            m = re.search('(.{4,40}?)(?:\\s*\\1){2,}', s, flags=re.S)
            if m:
                head = s[:m.start()]
                return (head + m.group(1)).strip()
            else:
                return s