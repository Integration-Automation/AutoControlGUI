import sys

if sys.platform not in ["darwin"]:
    raise Exception("should be only loaded on MacOS")

from je_auto_control.osx.listener.osx_listener import osx_record
from je_auto_control.osx.listener.osx_listener import osx_stop_record

from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlJsonActionException


class OSXRecorder(object):

    def record(self):
        osx_record()

    def stop_record(self):
        record_queue = osx_stop_record()
        if record_queue is None:
            raise AutoControlJsonActionException
        return osx_stop_record()


osx_recorder = OSXRecorder()

if __name__ == "__main__":
    test_osx_recorder = OSXRecorder()
    test_osx_recorder.record()
    temp = test_osx_recorder.stop_record()
    print(temp)
    for action in temp.queue:
        print(action)
    while True:
        pass
