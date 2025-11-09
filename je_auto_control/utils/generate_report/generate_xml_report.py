from threading import Lock
from typing import Tuple, Union
from xml.dom.minidom import parseString

from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import dict_to_elements_tree


def generate_xml() -> Tuple[Union[str, bytes], Union[str, bytes]]:
    """
    Generate XML strings from test records.
    從測試紀錄生成 XML 字串

    :return: (success_xml, failure_xml)
    """
    autocontrol_logger.info("generate_xml")

    success_dict, failure_dict = generate_json()
    success_dict = {"xml_data": success_dict}
    failure_dict = {"xml_data": failure_dict}

    success_xml = dict_to_elements_tree(success_dict)
    failure_xml = dict_to_elements_tree(failure_dict)

    return success_xml, failure_xml


def _write_xml_file(file_name: str, xml_content: str, lock: Lock) -> None:
    """
    Write XML content to file safely with lock.
    使用 Lock 安全地將 XML 內容寫入檔案

    :param file_name: 檔案名稱
    :param xml_content: XML 字串
    :param lock: 執行緒鎖
    """
    with lock:
        try:
            with open(file_name, "w+", encoding="utf-8") as file_to_write:
                file_to_write.write(xml_content)
        except Exception as error:
            autocontrol_logger.error(f"Failed to write {file_name}, error: {repr(error)}")


def generate_xml_report(xml_file_name: str = "default_name") -> None:
    """
    Output XML report files (success and failure).
    輸出 XML 報告檔案 (成功與失敗)

    :param xml_file_name: 檔案名稱前綴
    """
    autocontrol_logger.info(f"generate_xml_report, xml_file_name: {xml_file_name}")

    success_xml, failure_xml = generate_xml()

    # 格式化 XML 內容 Format XML content
    success_xml = parseString(success_xml).toprettyxml()
    failure_xml = parseString(failure_xml).toprettyxml()

    lock = Lock()
    _write_xml_file(xml_file_name + "_success.xml", success_xml, lock)
    _write_xml_file(xml_file_name + "_failure.xml", failure_xml, lock)