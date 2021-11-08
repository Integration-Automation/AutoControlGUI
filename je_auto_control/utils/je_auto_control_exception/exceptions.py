class AutoControlException(Exception):
    pass


class AutoControlKeyboardException(AutoControlException):
    pass


class AutoControlMouseException(AutoControlException):
    pass


class AutoControlScreenException(AutoControlException):
    pass


class AutoControlCantFindKeyException(AutoControlException):
    pass


class ImageNotFoundException(AutoControlException):
    pass


class AutoControlRecordException(AutoControlException):
    pass


class AutoControlJsonActionException(AutoControlException):
    pass


class AutoControlActionNullException(AutoControlException):
    pass
