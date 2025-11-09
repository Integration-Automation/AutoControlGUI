import threading
import cv2
import numpy as np
from mss import mss

from je_auto_control.utils.logging.loggin_instance import autocontrol_logger


class RecordingThread(threading.Thread):
    """
    RecordingThread
    螢幕錄影執行緒
    - 使用 mss 擷取螢幕畫面
    - 使用 OpenCV VideoWriter 寫入影片檔案
    """

    def __init__(self, video_name: str = "autocontrol_recording", fps: int = 20):
        super().__init__()
        autocontrol_logger.info("Init RecordingThread")
        self.recording_flag = True
        self.video_name = video_name
        self.daemon = True
        self.fps = fps

    def set_recording_flag(self, recording_flag: bool):
        """
        設定錄影旗標
        Set recording flag

        :param recording_flag: True = 繼續錄影, False = 停止錄影
        """
        autocontrol_logger.info(f"RecordingThread set_recording_flag: {recording_flag}")
        self.recording_flag = recording_flag

    def stop(self):
        """
        停止錄影
        Stop recording
        """
        self.set_recording_flag(False)

    def run(self):
        """
        執行錄影迴圈
        Run recording loop
        """
        with mss() as sct:
            resolution = sct.monitors[0]
            output_file = self.video_name + ".mp4"

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            video_writer = cv2.VideoWriter(
                output_file,
                fourcc,
                self.fps,
                (resolution["width"], resolution["height"])
            )

            if not video_writer.isOpened():
                autocontrol_logger.error("Failed to open VideoWriter")
                return

            try:
                while self.recording_flag:
                    # 擷取螢幕畫面 Capture screen frame
                    screen_image = sct.grab(resolution)
                    image_rgb = cv2.cvtColor(np.array(screen_image), cv2.COLOR_BGRA2BGR)
                    video_writer.write(image_rgb)
            except Exception as e:
                autocontrol_logger.error(f"RecordingThread error: {e}")
            finally:
                video_writer.release()
                autocontrol_logger.info("RecordingThread stopped and video released")