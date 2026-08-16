# general
class AutoControlException(Exception):
    """Base class for every AutoControl runtime error.

    All framework exceptions derive from this so that containment boundaries
    (executor, background poll loops, request handlers, GUI slots) can catch
    the whole family with a single ``except AutoControlException``. Do not add
    a sibling that inherits ``Exception`` directly — that silently escapes
    every such boundary.
    """


# Keyboard
class AutoControlKeyboardException(AutoControlException):
    pass


class AutoControlCantFindKeyException(AutoControlException):
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


class AutoControlFlatTemplateException(AutoControlScreenException):
    """Template has (almost) no variation, so normalised correlation degenerates.

    A subclass rather than a sibling, so existing ``except
    AutoControlScreenException`` handlers keep catching it; callers that want to
    tell the user what to do about it (crop something with a pattern in it) can
    catch this one specifically.
    """


# Record


class AutoControlRecordException(AutoControlException):
    pass


# Execute action

class AutoControlExecuteActionException(AutoControlException):
    pass


class AutoControlJsonActionException(AutoControlException):
    pass


class AutoControlActionNullException(AutoControlException):
    pass


class AutoControlActionException(AutoControlException):
    pass


class AutoControlAddCommandException(AutoControlException):
    pass


class AutoControlAssertionException(AutoControlException):
    """Raised when an ``AC_assert_*`` check fails."""


class AutoControlArgparseException(AutoControlException):
    pass


# html exception

class AutoControlHTMLException(AutoControlException):
    pass


# Json Exception

class AutoControlJsonException(AutoControlException):
    pass


class AutoControlGenerateJsonReportException(AutoControlException):
    pass


# XML

class XMLException(AutoControlException):
    pass


class XMLTypeException(AutoControlException):
    pass


# Execute callback
class CallbackExecutorException(AutoControlException):
    pass
