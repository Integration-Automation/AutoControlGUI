import sys
from queue import Queue

from je_auto_control.utils.exception.exception_tags import osx_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)

from je_auto_control.osx.listener.osx_listener import osx_record
from je_auto_control.osx.listener.osx_listener import osx_stop_record

from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException


class OSXRecorder(object):

    def __init__(self):
        self.record_flag = False

    def record(self) -> None:
        self.record_flag = True
        osx_record()

    def stop_record(self) -> Queue:
        record_queue = osx_stop_record()
        self.record_flag = False
        if record_queue is None:
            raise AutoControlJsonActionException
        return osx_stop_record()


osx_recorder = OSXRecorder()
