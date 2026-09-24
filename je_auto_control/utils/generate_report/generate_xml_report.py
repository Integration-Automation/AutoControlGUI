from typing import Tuple, Union

from defusedxml.minidom import parseString  # nosec B405  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml  # reason: defusedxml is the safe replacement

from je_auto_control.utils.exception.exceptions import XMLException
from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import dict_to_elements_tree


def generate_xml() -> Tuple[Union[str, bytes], Union[str, bytes]]:
    """
    Generate XML strings from test records.
    從測試紀錄生成 XML 字串

    :return: (success_xml, failure_xml)
    """
    autocontrol_logger.info("generate_xml")

    success_dict, failure_dict = generate_json()

    success_xml = dict_to_elements_tree({"xml_data": success_dict})
    failure_xml = dict_to_elements_tree({"xml_data": failure_dict})

    return success_xml, failure_xml


def _write_xml_file(file_name: str, xml_content: str) -> None:
    """Write ``xml_content`` atomically; raise :class:`XMLException` on failure.

    A failed write used to be logged and dropped, so callers and scripts went
    on as if the report existed.
    """
    try:
        atomic_write_text(file_name, xml_content)
    except OSError as error:
        raise XMLException(f"cannot write report {file_name!r}: {error!r}") from error


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

    _write_xml_file(xml_file_name + "_success.xml", success_xml)
    _write_xml_file(xml_file_name + "_failure.xml", failure_xml)
