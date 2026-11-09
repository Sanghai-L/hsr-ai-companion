"""Windows DPAPI protection for a local maintainer key, never a release payload."""
import ctypes
from ctypes import wintypes
import os

from companion.contracts import CompanionError, ErrorCode


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(content, protect):
    if os.name != "nt":
        raise CompanionError(ErrorCode.UNSUPPORTED, "维护者私钥使用当前 Windows 用户的 DPAPI")
    buffer = ctypes.create_string_buffer(content)
    source = Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt32 = ctypes.windll.crypt32
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(source), "HSR Companion release signing", None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise CompanionError(ErrorCode.INVALID_INPUT, "无法保护或解锁本机发布私钥")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def protect(content):
    return b"HSR-DPAPI-v1\n" + _crypt(content, True)


def unlock(path):
    content = path.read_bytes()
    if not content.startswith(b"HSR-DPAPI-v1\n") or len(content) > 65536:
        raise CompanionError(ErrorCode.INVALID_INPUT, "生产构建只接受受保护的本机私钥")
    return _crypt(content.split(b"\n", 1)[1], False)
