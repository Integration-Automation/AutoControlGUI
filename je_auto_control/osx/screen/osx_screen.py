import sys
import ctypes
from ctypes import c_void_p, c_uint32
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

import Quartz


class CGPoint(ctypes.Structure):
    """CoreGraphics CGPoint (two doubles)."""
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    """CoreGraphics CGSize (two doubles)."""
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class CGRect(ctypes.Structure):
    """CoreGraphics CGRect.

    Must be a real Structure, not ``c_double * 4``: ctypes passes an array
    argument as a *pointer*, whereas CGWindowListCreateImage takes its CGRect
    **by value**. The array form made the capture rect garbage.
    """
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


def size() -> Tuple[int, int]:
    """
    Get screen size
    取得螢幕大小 (寬度, 高度)

    :return: (width, height) 螢幕寬度與高度
    """
    return (
        Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID()),
        Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
    )


def get_pixel(x: int, y: int) -> Tuple[int, int, int]:
    """
    Get RGB value of pixel at given coordinates
    取得指定座標的像素 RGB 值

    回傳 RGB 以與 windows / x11 / wayland 後端一致：先前回傳 RGBA，
    使得 ``r, g, b = get_pixel(...)`` 只在 macOS 上失敗。
    Returns RGB to match the windows / x11 / wayland backends. This previously
    returned RGBA, so ``r, g, b = get_pixel(...)`` unpacked fine everywhere
    except macOS.

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :return: (R, G, B) 三原色值
    """
    # 載入 CoreGraphics 與 CoreFoundation 函式庫
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    # 設定函式簽名 Function signatures
    cg.CGWindowListCreateImage.argtypes = [CGRect, c_uint32, c_uint32, c_uint32]
    cg.CGWindowListCreateImage.restype = c_void_p

    cg.CGImageGetDataProvider.argtypes = [c_void_p]
    cg.CGImageGetDataProvider.restype = c_void_p

    cg.CGDataProviderCopyData.argtypes = [c_void_p]
    cg.CGDataProviderCopyData.restype = c_void_p

    cf.CFDataGetLength.argtypes = [c_void_p]
    cf.CFDataGetLength.restype = ctypes.c_long

    cf.CFDataGetBytePtr.argtypes = [c_void_p]
    cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)

    cf.CFRelease.argtypes = [c_void_p]
    cf.CFRelease.restype = None

    # 常數 Constants (Apple names: kCGWindowListOptionOnScreenOnly,
    # kCGNullWindowID, kCGWindowImageDefault)
    window_list_option_on_screen_only = 1
    null_window_id = 0
    window_image_default = 0

    # 建立擷取範圍 Create capture rect
    rect = CGRect(CGPoint(float(x), float(y)), CGSize(1.0, 1.0))

    # 擷取螢幕影像 Capture screen image
    img = cg.CGWindowListCreateImage(
        rect,
        window_list_option_on_screen_only,
        null_window_id,
        window_image_default
    )
    if not img:
        raise RuntimeError(
            "Unable to capture screen image. 請確認已授予螢幕錄製權限"
        )

    cfdata = None
    try:
        # 取得影像資料供應器 Get data provider
        # CGImageGetDataProvider 是 "Get" 函式，呼叫端不擁有這個參考，
        # 因此絕對不可以 CFRelease，否則會過度釋放。
        # Per the CoreFoundation Get Rule, a "Get" function does not transfer
        # ownership: releasing `provider` here underflowed its refcount, and
        # releasing `img` below (which owns the provider) then freed it again.
        provider = cg.CGImageGetDataProvider(img)

        # 複製影像資料 Copy image data
        cfdata = cg.CGDataProviderCopyData(provider)

        # 取得資料長度 Get data length
        length = cf.CFDataGetLength(cfdata)
        if length < 4:
            raise RuntimeError("Invalid pixel data. 資料不足")

        # 取得 byte pointer Get byte pointer
        buf = cf.CFDataGetBytePtr(cfdata)

        # 預設像素格式為 BGRA；捨棄 alpha 以符合其他後端的 RGB 回傳。
        # Pixel format is BGRA; drop alpha so the return matches the other
        # backends' RGB.
        b, g, r = buf[0], buf[1], buf[2]

        return r, g, b
    finally:
        # 只釋放自己擁有的物件：cfdata 來自 "Copy"、img 來自 "Create"。
        # provider 來自 "Get"，不屬於我們，不能釋放。
        # Release only what we own: cfdata came from a Copy function and img
        # from a Create function. provider came from a Get function.
        if cfdata:
            cf.CFRelease(cfdata)
        cf.CFRelease(img)