import sys
import ctypes
from ctypes import c_void_p, c_double, c_uint32
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

import Quartz


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


def get_pixel(x: int, y: int) -> Tuple[int, int, int, int]:
    """
    Get RGBA value of pixel at given coordinates
    取得指定座標的像素 RGBA 值

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :return: (R, G, B, A) 四原色值
    """
    # 載入 CoreGraphics 與 CoreFoundation 函式庫
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    # 定義 CGRect 結構 (x, y, width, height)
    CGRect = ctypes.c_double * 4

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

    # 常數 Constants
    kCGWindowListOptionOnScreenOnly = 1
    kCGNullWindowID = 0
    kCGWindowImageDefault = 0

    # 建立擷取範圍 Create capture rect
    rect = CGRect(x, y, 1.0, 1.0)

    # 擷取螢幕影像 Capture screen image
    img = cg.CGWindowListCreateImage(
        rect,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault
    )
    if not img:
        raise RuntimeError(
            "Unable to capture screen image. 請確認已授予螢幕錄製權限"
        )

    # 取得影像資料供應器 Get data provider
    provider = cg.CGImageGetDataProvider(img)

    # 複製影像資料 Copy image data
    cfdata = cg.CGDataProviderCopyData(provider)

    # 取得資料長度 Get data length
    length = cf.CFDataGetLength(cfdata)
    if length < 4:
        cf.CFRelease(cfdata)
        cf.CFRelease(provider)
        cf.CFRelease(img)
        raise RuntimeError("Invalid pixel data. 資料不足")

    # 取得 byte pointer Get byte pointer
    buf = cf.CFDataGetBytePtr(cfdata)

    # 預設像素格式為 BGRA Default pixel format is BGRA
    b, g, r, a = buf[0], buf[1], buf[2], buf[3]

    # 釋放 CoreFoundation 物件 Release CF objects
    cf.CFRelease(cfdata)
    cf.CFRelease(provider)
    cf.CFRelease(img)

    return r, g, b, a