import sys
from threading import Lock
from xml.dom.minidom import parseString
from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import dict_to_elements_tree


def generate_xml():
    """
    :return:
    """
    success_dict, failure_dict = generate_json()
    success_dict = dict({"xml_data": success_dict})
    failure_dict = dict({"xml_data": failure_dict})
    success_json_to_xml = dict_to_elements_tree(success_dict)
    failure_json_to_xml = dict_to_elements_tree(failure_dict)
    return success_json_to_xml, failure_json_to_xml


def generate_xml_report(xml_file_name: str = "default_name"):
    """
    :param xml_file_name:
    """
    success_xml, failure_xml = generate_xml()
    success_xml = parseString(success_xml)
    failure_xml = parseString(failure_xml)
    success_xml = success_xml.toprettyxml()
    failure_xml = failure_xml.toprettyxml()
    lock = Lock()
    try:
        lock.acquire()
        with open(xml_file_name + "_failure.xml", "w+") as file_to_write:
            file_to_write.write(failure_xml)
    except Exception as error:
        print(repr(error), file=sys.stderr)
    finally:
        lock.release()
    try:
        lock.acquire()
        with open(xml_file_name + "_success.xml", "w+") as file_to_write:
            file_to_write.write(success_xml)
            pass
    except Exception as error:
        print(repr(error), file=sys.stderr)
    finally:
        lock.release()

