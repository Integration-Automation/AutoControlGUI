import threading
from typing import Dict, Tuple
import cv2

from je_auto_control.wrapper.auto_control_screen import screenshot


class ScreenRecorder:
    """
    ScreenRecorder
    螢幕錄影器管理類別
    - 可同時管理多個錄影執行緒
    """

    def __init__(self):
        self.running_recorder: Dict[str, ScreenRecordThread] = {}

    def start_new_record(
        self,
        recorder_name: str,
        path_and_filename: str = "output.avi",
        codec: str = "XVID",
        frame_per_sec: int = 30,
        resolution: Tuple[int, int] = (1920, 1080)
    ):
        """
        Start a new screen recording
        開始新的螢幕錄影

        :param recorder_name: 錄影器名稱
        :param path_and_filename: 輸出檔案名稱
        :param codec: 編碼器 (例如 "XVID")
        :param frame_per_sec: 每秒幀數
        :param resolution: 解析度 (寬, 高)
        """
        record_thread = ScreenRecordThread(path_and_filename, codec, frame_per_sec, resolution)

        # 如果已有同名錄影器，先停止舊的
        old_record = self.running_recorder.get(recorder_name)
        if old_record is not None:
            old_record.stop()

        record_thread.daemon = True
        record_thread.start()
        self.running_recorder[recorder_name] = record_thread

    def stop_record(self, recorder_name: str):
        """
        Stop a specific recorder
        停止指定的錄影器
        """
        if recorder_name in self.running_recorder:
            self.running_recorder[recorder_name].stop()
            del self.running_recorder[recorder_name]


class ScreenRecordThread(threading.Thread):
    """
    ScreenRecordThread
    螢幕錄影執行緒
    - 持續擷取螢幕畫面並寫入影片檔案
    """

    def __init__(self, path_and_filename, codec, frame_per_sec, resolution: Tuple[int, int]):
        super().__init__()
        self.fourcc = cv2.VideoWriter.fourcc(*codec)
        self.video_writer = cv2.VideoWriter(path_and_filename, self.fourcc, frame_per_sec, resolution)
        self.record_flag = False
        self.resolution = resolution

    def run(self) -> None:
        self.record_flag = True
        while self.record_flag:
            # 擷取螢幕畫面 Capture screen frame
            image = screenshot()

            # 確保影像大小符合設定解析度 Ensure frame size matches resolution
            if image.shape[1] != self.resolution[0] or image.shape[0] != self.resolution[1]:
                image = cv2.resize(image, self.resolution)

            self.video_writer.write(image)

        # 錄影結束後釋放資源 Release resources after recording
        self.video_writer.release()

    def stop(self) -> None:
        """
        Stop recording
        停止錄影
        """
        self.record_flag = False