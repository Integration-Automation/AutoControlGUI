import threading

import cv2
import numpy as np
from mss import mss

from je_auto_control.utils.logging.loggin_instance import autocontrol_logger


class RecordingThread(threading.Thread):

    def __init__(self, video_name: str = "autocontrol_recoding"):
        autocontrol_logger.info("Init RecordingThread")
        super().__init__()
        self.recoding_flag = True
        self.video_name = video_name

    def set_recoding_flag(self, recoding_flag: bool):
        autocontrol_logger.info(f"RecordingThread set_recoding_flag recoding_flag: {recoding_flag}")
        self.recoding_flag = recoding_flag

    def run(self):
        with mss() as sct:
            resolution = sct.monitors[0]
            self.video_name = self.video_name + '.mp4'
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            desired_fps = 20
            video_writer = cv2.VideoWriter(self.video_name, fourcc, desired_fps,
                                           (resolution['width'], resolution['height']))
            while self.recoding_flag:
                screen_image = sct.grab(resolution)
                image_rgb = cv2.cvtColor(np.array(screen_image), cv2.COLOR_BGRA2BGR)
                video_writer.write(image_rgb)
            else:
                video_writer.release()
