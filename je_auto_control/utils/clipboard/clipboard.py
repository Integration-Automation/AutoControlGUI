"""Headless cross-platform text + image clipboard.

Windows uses Win32 clipboard API via ctypes (CF_UNICODETEXT for text,
CF_DIB for image).
macOS shells out to pbcopy / pbpaste for text; image support requires
PyObjC and is best effort.
Linux shells out to xclip / xsel for text and ``xclip -t image/png`` for
images.

All functions raise ``RuntimeError`` if the platform backend is missing so
callers can degrade gracefully.
"""
import shutil
import subprocess  # nosec B404  # reason: required for pbcopy/pbpaste/xclip/xsel
import sys
from io import BytesIO
from typing import Optional


def get_clipboard() -> str:
    """Return the current clipboard text (empty string if empty)."""
    if sys.platform.startswith("win"):
        return _win_get()
    if sys.platform == "darwin":
        return _mac_get()
    return _linux_get()


def set_clipboard(text: str) -> None:
    """Replace clipboard contents with ``text``."""
    if not isinstance(text, str):
        raise TypeError("set_clipboard expects a str")
    if sys.platform.startswith("win"):
        _win_set(text)
        return
    if sys.platform == "darwin":
        _mac_set(text)
        return
    _linux_set(text)


def get_clipboard_image() -> Optional[bytes]:
    """Return the clipboard's image as PNG bytes, or ``None`` if no image."""
    if sys.platform.startswith("win"):
        return _win_get_image()
    if sys.platform == "darwin":
        return _mac_get_image()
    return _linux_get_image()


def set_clipboard_image(png_bytes: bytes) -> None:
    """Place a PNG image (as bytes) onto the clipboard."""
    if not isinstance(png_bytes, (bytes, bytearray)):
        raise TypeError("set_clipboard_image expects bytes")
    if not png_bytes:
        raise ValueError("png_bytes is empty")
    if sys.platform.startswith("win"):
        _win_set_image(bytes(png_bytes))
        return
    if sys.platform == "darwin":
        _mac_set_image(bytes(png_bytes))
        return
    _linux_set_image(bytes(png_bytes))


# === Windows backend =========================================================

def _win_get() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cf_unicodetext = 13

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        handle = user32.GetClipboardData(cf_unicodetext)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _win_set(text: str) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cf_unicodetext = 13
    gmem_moveable = 0x0002

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)  # NOSONAR S5655 false positive — Array is accepted by sizeof
    handle = kernel32.GlobalAlloc(gmem_moveable, size)
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise RuntimeError("GlobalLock failed")
    ctypes.memmove(pointer, ctypes.addressof(data), size)  # NOSONAR S5655 false positive — Array is accepted by addressof
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(cf_unicodetext, handle):
            raise RuntimeError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()


# === macOS backend ===========================================================

def _mac_get() -> str:
    result = subprocess.run(  # nosec B603 B607  # reason: hard-coded macOS clipboard tool, argv list
        ["pbpaste"], capture_output=True, check=True, timeout=5,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _mac_set(text: str) -> None:
    subprocess.run(  # nosec B603 B607  # reason: hard-coded macOS clipboard tool, argv list
        ["pbcopy"], input=text.encode("utf-8"),
        check=True, timeout=5,
    )


# === Linux backend ===========================================================

def _linux_cmd() -> Optional[list]:
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard"]
    return None


def _linux_get() -> str:
    cmd = _linux_cmd()
    if cmd is None:
        raise RuntimeError("Install xclip or xsel for Linux clipboard support")
    read_cmd = cmd + ["-o"] if cmd[0] == "xclip" else cmd + ["--output"]
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    result = subprocess.run(  # nosec B603  # reason: argv from allowlist (xclip/xsel) discovered via shutil.which
        read_cmd, capture_output=True, check=True, timeout=5,
    )
    return result.stdout.decode("utf-8", errors="replace")


def _linux_set(text: str) -> None:
    cmd = _linux_cmd()
    if cmd is None:
        raise RuntimeError("Install xclip or xsel for Linux clipboard support")
    write_cmd = cmd + ["-i"] if cmd[0] == "xclip" else cmd + ["--input"]
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    subprocess.run(  # nosec B603  # reason: argv from allowlist (xclip/xsel) discovered via shutil.which
        write_cmd, input=text.encode("utf-8"),
        check=True, timeout=5,
    )


# === Image clipboard backends ===============================================


def _win_get_image() -> Optional[bytes]:
    """Return the Windows clipboard image as PNG bytes, or None."""
    try:
        from PIL import ImageGrab  # noqa: PLC0415  lazy import
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required for clipboard image support"
        ) from error
    image = ImageGrab.grabclipboard()
    if image is None or isinstance(image, list):
        return None
    buffer = BytesIO()
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _win_set_image(png_bytes: bytes) -> None:
    """Set the Windows clipboard image from PNG bytes (CF_DIB)."""
    try:
        from PIL import Image  # noqa: PLC0415  lazy import
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required for clipboard image support"
        ) from error
    image = Image.open(BytesIO(png_bytes))
    if image.mode != "RGB":
        image = image.convert("RGB")
    bmp_buf = BytesIO()
    image.save(bmp_buf, format="BMP")
    # CF_DIB excludes the 14-byte BITMAPFILEHEADER prefix that BMP files use.
    dib = bmp_buf.getvalue()[14:]

    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    cf_dib = 8
    gmem_moveable = 0x0002

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    handle = kernel32.GlobalAlloc(gmem_moveable, len(dib))
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise RuntimeError("GlobalLock failed")
    ctypes.memmove(pointer, dib, len(dib))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(cf_dib, handle):
            raise RuntimeError("SetClipboardData(CF_DIB) failed")
    finally:
        user32.CloseClipboard()


def _mac_get_image() -> Optional[bytes]:
    """Read clipboard image via Pillow's ImageGrab; raises if PIL missing."""
    try:
        from PIL import ImageGrab  # noqa: PLC0415
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required for clipboard image support on macOS"
        ) from error
    image = ImageGrab.grabclipboard()
    if image is None or isinstance(image, list):
        return None
    buffer = BytesIO()
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _mac_set_image(_png_bytes: bytes) -> None:
    raise RuntimeError(
        "Setting clipboard images on macOS requires PyObjC; not yet supported"
    )


def _linux_get_image() -> Optional[bytes]:
    if not shutil.which("xclip"):
        raise RuntimeError("Install xclip for Linux clipboard image support")
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    result = subprocess.run(  # nosec B603 B607  # reason: hard-coded argv to xclip
        ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
        capture_output=True, check=False, timeout=5,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return result.stdout


def _linux_set_image(png_bytes: bytes) -> None:
    if not shutil.which("xclip"):
        raise RuntimeError("Install xclip for Linux clipboard image support")
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    subprocess.run(  # nosec B603 B607  # reason: hard-coded argv to xclip
        ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
        input=png_bytes, check=True, timeout=5,
    )
