"""Bounded local paths, including Windows reparse points and junctions."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path, PureWindowsPath
import re
import time
import uuid

from companion.contracts import CompanionError, ErrorCode

_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def _reject_link(path):
    if path.exists() or path.is_symlink():
        stat = path.lstat()
        if path.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
            raise CompanionError(ErrorCode.INVALID_INPUT, "不允许符号链接或 Windows junction", details={"name": path.name})


class SafeRoot:
    def __init__(self, root):
        raw = Path(os.path.abspath(root))
        for node in reversed([raw, *raw.parents]):
            _reject_link(node)
        raw.mkdir(parents=True, exist_ok=True)
        _reject_link(raw)
        self.root = raw.resolve(strict=True)

    def path(self, relative):
        raw = str(relative).replace("\\", "/")
        parts = raw.split("/")
        windows = PureWindowsPath(raw)
        if (not raw or windows.is_absolute() or windows.drive or any(
                not p or p in {".", ".."} or ":" in p or p.endswith((" ", ".")) or
                any(ord(c) < 32 or c in '<>"|?*' for c in p) or _RESERVED.match(p) for p in parts)):
            raise CompanionError(ErrorCode.INVALID_INPUT, "路径必须位于指定数据根内")
        _reject_link(self.root)
        path = self.root
        for part in parts:
            path = path / part
            _reject_link(path)
        if not path.resolve().is_relative_to(self.root):
            raise CompanionError(ErrorCode.INVALID_INPUT, "路径越界")
        return path

    def mkdir(self, relative):
        path = self.path(relative)
        path.mkdir(parents=True, exist_ok=True)
        return self.path(relative)

    def write(self, relative, content: bytes, *, exclusive=False):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self.path(relative)
        if exclusive:
            with path.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            return path
        temporary = path.with_name("tmp-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.path(relative)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path


@contextmanager
def file_lock(root: SafeRoot, name="lock", *, timeout=10, shared=False):
    """OS releases this lock on process death; no stale PID deletion."""
    path = root.path(name)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        start = time.monotonic()
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt
            class Overlapped(ctypes.Structure):
                _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                            ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]
            overlap = Overlapped()
            handle = wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno()))
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
            kernel.LockFileEx.restype = wintypes.BOOL
            kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
            kernel.UnlockFileEx.restype = wintypes.BOOL
        while True:
            stream.seek(0)
            try:
                if os.name == "nt":
                    if not kernel.LockFileEx(handle, 1 | (0 if shared else 2), 0, 1, 0, ctypes.byref(overlap)):
                        raise ctypes.WinError(ctypes.get_last_error())
                else:
                    import fcntl
                    fcntl.flock(stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() - start >= timeout:
                    raise CompanionError(ErrorCode.CONFLICT, "另一个本地操作正在执行", retryable=True)
                time.sleep(0.02)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                if not kernel.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(overlap)):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_UN)

