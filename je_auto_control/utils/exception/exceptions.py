# general
class AutoControlException(Exception):
    pass


# Keyboard
class AutoControlKeyboardException(Exception):
    pass


class AutoControlCantFindKeyException(Exception):
    pass


# Mouse
class AutoControlMouseException(Exception):
    pass


# Screen


class AutoControlScreenException(Exception):
    pass


# Image detect


class ImageNotFoundException(Exception):
    pass


# Record


class AutoControlRecordException(Exception):
    pass


# Execute action

class AutoControlExecuteActionException(Exception):
    pass


class AutoControlJsonActionException(Exception):
    pass


class AutoControlActionNullException(Exception):
    pass


class AutoControlActionException(Exception):
    pass


class AutoControlAddCommandException(Exception):
    pass


class AutoControlArgparseException(Exception):
    pass


# timeout
class AutoControlTimeoutException(Exception):
    pass


# html exception

class AutoControlHTMLException(Exception):
    pass


# Json Exception

class AutoControlJsonException(Exception):
    pass


class AutoControlGenerateJsonReportException(Exception):
    pass


# XML

class XMLException(Exception):
    pass


class XMLTypeException(Exception):
    pass


# Execute callback
class CallbackExecutorException(Exception):
    pass
