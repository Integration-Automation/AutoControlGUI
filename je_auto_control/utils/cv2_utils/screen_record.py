import threading
from typing import Dict, Tuple

from cv2 import VideoWriter

from je_auto_control.wrapper.auto_control_screen import screenshot


class ScreenRecorder(object):

    def __init__(self):
        self.running_recorder: Dict[str, ScreenRecordThread] = {}

    def start_new_recode(self, recoder_name: str, path_and_filename: str = "output.avi", codec: str = "XVID",
                         frame_per_sec: int = 30, resolution: Tuple[int, int] = (1920, 1080)):
        record_thread = ScreenRecordThread(path_and_filename, codec, frame_per_sec, resolution)
        old_record = self.running_recorder.get(recoder_name, None)
        if old_record is not None:
            old_record.record_flag = False
        record_thread.daemon = True
        record_thread.start()
        self.running_recorder.update({recoder_name: record_thread})


class ScreenRecordThread(threading.Thread):

    def __init__(self, path_and_filename, codec, frame_per_sec, resolution: Tuple[int, int]):
        super().__init__()
        self.fourcc = VideoWriter.fourcc(*codec)
        self.video_writer = VideoWriter(path_and_filename, self.fourcc, frame_per_sec, resolution)
        self.record_flag = False

    def run(self) -> None:
        self.record_flag = True
        while self.record_flag:
            # Get raw pixels from the screen, save it to a Numpy array
            image = screenshot()
            self.video_writer.write(image)
        else:
            self.video_writer.release()
