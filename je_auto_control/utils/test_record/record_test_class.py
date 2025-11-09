import datetime
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger


class TestRecord:
    """
    TestRecord
    測試紀錄管理類別
    - 控制是否啟用紀錄
    - 儲存測試紀錄清單
    """

    def __init__(self, init_record: bool = False):
        """
        初始化 TestRecord
        Initialize TestRecord

        :param init_record: 是否啟用紀錄 Flag to enable recording
        """
        self.init_record: bool = init_record
        self.test_record_list: list[dict] = []

    def clean_record(self) -> None:
        """
        清空紀錄
        Clear all records
        """
        self.test_record_list = []

    def set_record_enable(self, set_enable: bool = True) -> None:
        """
        設定是否啟用紀錄
        Enable or disable recording

        :param set_enable: True = 啟用, False = 停用
        """
        autocontrol_logger.info(f"set_record_enable, set_enable: {set_enable}")
        self.init_record = set_enable


# 全域測試紀錄實例 Global test record instance
test_record_instance = TestRecord()


def record_action_to_list(function_name: str, local_param, program_exception: str = None) -> None:
    """
    將動作紀錄加入清單
    Record action to list

    :param function_name: 函式名稱 Function name
    :param local_param: 執行參數 Local parameters
    :param program_exception: 例外訊息 Exception message (預設 None)
    """
    if not test_record_instance.init_record:
        return

    test_record_instance.test_record_list.append(
        {
            "function_name": function_name,
            "local_param": local_param,
            "time": datetime.datetime.now().isoformat(),  # 使用 ISO 格式更標準
            "program_exception": repr(program_exception),
        }
    )