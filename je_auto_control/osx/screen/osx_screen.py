import Quartz


def size():
    return Quartz.CGDisplayPixelsWide((Quartz.CGMainDisplayID())), Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
