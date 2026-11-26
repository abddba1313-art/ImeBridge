# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'secret.py'
# Bytecode version: 3.12.0rc2 (3531)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""API Key 的落盘加密：Windows DPAPI（crypt32，当前用户范围），零第三方依赖。\n\n为什么不能把 Key 直接写进 config.json：\n配置文件是明文，%APPDATA% 会被备份、被同步盘上传、被用户整包打包发给别人\n（这次就是用户要把配置界面交出来讨论）。Key 明文躺在里面，等于随手分发。\n\nDPAPI 用当前用户的登录凭据派生密钥，密文只有**同一台机器上的同一个 Windows 用户**\n能解出来。它挡不住管理员，也挡不住\"用户自己把 Key 显示在界面上\"，\n但足以挡住上面那几条最常见的泄漏路径。附带一段固定 entropy（写在程序里），\n作用是提高门槛：别的程序在自己的进程里调 CryptUnprotectData 解不开，\n必须先知道这段 entropy —— 说清楚，这是加难度，不是一堵加密墙。\n"""
import base64
import ctypes
from ctypes import wintypes
_ENTROPY = b'ImeBridge/apikey/v2.3/2026-10-10'
CRYPTPROTECT_UI_FORBIDDEN = 1
class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]
def _blob(data: bytes) -> DATA_BLOB:
    b = DATA_BLOB()
    b.cbData = len(data)
    buf = ctypes.create_string_buffer(data, len(data))
    b.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    b._buf = buf
    return b
def _take(out_blob: DATA_BLOB) -> bytes:
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        try:
            ctypes.windll.crypt32.CryptFreeDataBuffer(out_blob.pbData)
        except Exception:
            pass
def protect(plain: str) -> str:
    """明文 → base64 密文。空串原样返回空串。失败时抛异常（调用方决定降级策略）。"""
    if not plain:
        return ''
    else:
        in_blob = _blob(plain.encode('utf-8'))
        ent = _blob(_ENTROPY)
        out_blob = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(in_blob), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
        if not ok:
            raise OSError('CryptProtectData 调用失败')
        else:
            return base64.b64encode(_take(out_blob)).decode('ascii')
def unprotect(cipher_b64: str) -> str:
    """base64 密文 → 明文。解不开（换了机器/换了用户/密文损坏）返回空串，\n    让\"API Key 为空\"变成一个可见的、可修的状态，而不是一个崩溃。"""
    if not cipher_b64:
        return ''
    else:
        try:
            raw = base64.b64decode(cipher_b64)
        except Exception:
            return ''
        in_blob = _blob(raw)
        ent = _blob(_ENTROPY)
        out_blob = DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, ctypes.byref(ent), None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob))
        if not ok:
            return ''
        else:
            data = _take(out_blob)
            try:
                return data.decode('utf-8')
            except Exception:
                return ''
def looks_encrypted(value: str) -> bool:
    """粗判：DPAPI 密文是 base64 且解得开；明文 Key 一般不含 \'/\'、\'=\' 的 base64 形态。"""
    if not value:
        return False
    else:
        try:
            raw = base64.b64decode(value, validate=True)
        except Exception:
            return False
        return len(raw) > 16