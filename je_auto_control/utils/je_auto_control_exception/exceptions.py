from je_auto_control.utils.je_auto_control_exception.exception_tag import cant_find_image
from je_auto_control.utils.je_auto_control_exception.exception_tag import table_cant_find_key
from je_auto_control.utils.je_auto_control_exception.exception_tag import je_auto_control_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import mouse_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import screen_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import record_queue_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import cant_find_json_error
from je_auto_control.utils.je_auto_control_exception.exception_tag import action_is_null_error


class AutoControlException(Exception):

    def __init__(self, message=je_auto_control_error):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return self.message


class AutoControlKeyboardException(AutoControlException):

    def __init__(self, message=keyboard_error):
        super().__init__(message)


class AutoControlMouseException(AutoControlException):
    def __init__(self, message=mouse_error):
        super().__init__(message)


class AutoControlScreenException(AutoControlException):
    def __init__(self, message=screen_error):
        super().__init__(message)


class AutoControlCantFindKeyException(AutoControlException):
    def __init__(self, message=table_cant_find_key):
        super().__init__(message)


class ImageNotFoundException(AutoControlException):

    def __init__(self, image, message=cant_find_image):
        self.image = image
        super().__init__(message)

    def __str__(self):
        return "{%s} cause by: {%s}" % (self.message, self.image)


class AutoControlRecordException(AutoControlException):
    def __init__(self, message=record_queue_error):
        super().__init__(message)


class AutoControlJsonActionException(AutoControlException):
    def __init__(self, message=cant_find_json_error):
        super().__init__(message)


class AutoControlActionNullException(AutoControlException):
    def __init__(self, message=action_is_null_error):
        super().__init__(message)



