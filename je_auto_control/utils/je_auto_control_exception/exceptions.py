"""
general
"""


class AutoControlException(Exception):
    pass


"""
Keyboard
"""


class AutoControlKeyboardException(AutoControlException):
    pass


class AutoControlCantFindKeyException(AutoControlException):
    pass


"""
Mouse
"""


class AutoControlMouseException(AutoControlException):
    pass


"""
Screen
"""


class AutoControlScreenException(AutoControlException):
    pass


"""
Image detect
"""


class ImageNotFoundException(AutoControlException):
    pass


"""
Record
"""


class AutoControlRecordException(AutoControlException):
    pass


"""
Execute action 
"""


class AutoControlJsonActionException(AutoControlException):
    pass


class AutoControlActionNullException(AutoControlException):
    pass


class AutoControlActionException(AutoControlException):
    pass
