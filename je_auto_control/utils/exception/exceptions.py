# general
class AutoControlException(Exception):
    pass


# Keyboard


class AutoControlKeyboardException(AutoControlException):
    pass


class AutoControlCantFindKeyException(AutoControlKeyboardException):
    pass


# Mouse


class AutoControlMouseException(AutoControlException):
    pass


# Screen


class AutoControlScreenException(AutoControlException):
    pass


# Image detect


class ImageNotFoundException(AutoControlException):
    pass


# Record


class AutoControlRecordException(AutoControlException):
    pass


# Execute action

class AutoControlExecuteActionException(AutoControlException):
    pass


class AutoControlJsonActionException(AutoControlExecuteActionException):
    pass


class AutoControlActionNullException(AutoControlExecuteActionException):
    pass


class AutoControlActionException(AutoControlExecuteActionException):
    pass


class AutoControlAddCommandException(AutoControlExecuteActionException):
    pass


class AutoControlArgparseException(AutoControlExecuteActionException):
    pass


# timeout
class AutoControlTimeoutException(AutoControlException):
    pass


# html exception

class AutoControlHTMLException(AutoControlException):
    pass


# Json Exception

class AutoControlJsonException(AutoControlException):
    pass


class AutoControlGenerateJsonReportException(AutoControlJsonException):
    pass


# XML

class XMLException(AutoControlException):
    pass


class XMLTypeException(XMLException):
    pass


# Execute callback
class CallbackExecutorException(AutoControlException):
    pass
