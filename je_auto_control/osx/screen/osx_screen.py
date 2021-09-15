import Quartz


def size():
    """
    get screen size
    """
    return Quartz.CGDisplayPixelsWide((Quartz.CGMainDisplayID())), Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
