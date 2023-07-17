from threading import Lock
from typing import Tuple, Union
from xml.dom.minidom import parseString

from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.logging.loggin_instance import auto_control_logger
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import dict_to_elements_tree


def generate_xml() -> Tuple[Union[str, bytes], Union[str, bytes]]:
    auto_control_logger.info("generate_xml")
    """
    :return: two dict {success_dict}, {failure_dict}
    """
    success_dict, failure_dict = generate_json()
    success_dict = dict({"xml_data": success_dict})
    failure_dict = dict({"xml_data": failure_dict})
    success_json_to_xml = dict_to_elements_tree(success_dict)
    failure_json_to_xml = dict_to_elements_tree(failure_dict)
    return success_json_to_xml, failure_json_to_xml


def generate_xml_report(xml_file_name: str = "default_name"):
    auto_control_logger.info(f"generate_xml_report, xml_file_name: {xml_file_name}")
    """
    :param xml_file_name: save xml file name
    """
    success_xml, failure_xml = generate_xml()
    success_xml = parseString(success_xml)
    failure_xml = parseString(failure_xml)
    success_xml = success_xml.toprettyxml()
    failure_xml = failure_xml.toprettyxml()
    lock = Lock()
    lock.acquire()
    try:
        with open(xml_file_name + "_failure.xml", "w+") as file_to_write:
            file_to_write.write(failure_xml)
    except Exception as error:
        auto_control_logger.error(
            f"generate_xml_report, xml_file_name: {xml_file_name}, "
            f"failed: {repr(error)}")
    finally:
        lock.release()
    lock.acquire()
    try:
        with open(xml_file_name + "_success.xml", "w+") as file_to_write:
            file_to_write.write(success_xml)
    except Exception as error:
        auto_control_logger.error(
            f"generate_xml_report, xml_file_name: {xml_file_name}, "
            f"failed: {repr(error)}")
    finally:
        lock.release()
