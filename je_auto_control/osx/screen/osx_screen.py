import sys
import ctypes
from ctypes import c_void_p, c_double, c_uint32
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import osx_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

import Quartz


def size() -> Tuple[int, int]:
    """
    get screen size
    """
    return Quartz.CGDisplayPixelsWide((Quartz.CGMainDisplayID())), Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())

def get_pixel(x: int, y: int) -> Tuple[int, int, int, int]:
    # Load CoreGraphics and CoreFoundation frameworks
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    # Define CGRect structure as 4 doubles: x, y, width, height
    CGRect = ctypes.c_double * 4

    # Function signatures
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

    # Constants
    kCGWindowListOptionOnScreenOnly = 1
    kCGNullWindowID = 0
    kCGWindowImageDefault = 0
    rect = CGRect(x, y, 1.0, 1.0)
    img = cg.CGWindowListCreateImage(rect,
                                     kCGWindowListOptionOnScreenOnly,
                                     kCGNullWindowID,
                                     kCGWindowImageDefault)
    if not img:
        raise RuntimeError("Unable to capture screen image. Please ensure Screen Recording permission is granted.")

    # Get the data provider from the image
    provider = cg.CGImageGetDataProvider(img)
    # Copy image data
    cfdata = cg.CGDataProviderCopyData(provider)
    # Get length of data
    length = cf.CFDataGetLength(cfdata)
    # Get pointer to byte data
    buf = cf.CFDataGetBytePtr(cfdata)

    # Default pixel format is BGRA
    b, g, r, a = buf[0], buf[1], buf[2], buf[3]

    # Release CoreFoundation objects to avoid memory leaks
    cf.CFRelease(cfdata)
    cf.CFRelease(provider)
    cf.CFRelease(img)

    return r, g, b, a

