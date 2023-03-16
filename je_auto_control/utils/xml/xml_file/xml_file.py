import xml.dom.minidom
from xml.etree import ElementTree

from je_auto_control.utils.exception.exception_tags import cant_read_xml_error
from je_auto_control.utils.exception.exception_tags import xml_type_error
from je_auto_control.utils.exception.exceptions import XMLException
from je_auto_control.utils.exception.exceptions import XMLTypeException


def reformat_xml_file(xml_string: str):
    dom = xml.dom.minidom.parseString(xml_string)
    return dom.toprettyxml()


class XMLParser(object):

    def __init__(self, xml_string: str, xml_type: str = "string"):
        """
        :param xml_string: full xml string
        :param xml_type: file or string
        """
        self.element_tree = ElementTree
        self.tree = None
        self.xml_root = None
        self.xml_from_type = "string"
        self.xml_string = xml_string.strip()
        xml_type = xml_type.lower()
        if xml_type not in ["file", "string"]:
            raise XMLTypeException(xml_type_error)
        if xml_type == "string":
            self.xml_parser_from_string()
        else:
            self.xml_parser_from_file()

    def xml_parser_from_string(self, **kwargs):
        """
        :param kwargs: any another param
        :return: xml root element tree
        """
        try:
            self.xml_root = ElementTree.fromstring(self.xml_string, **kwargs)
        except XMLException:
            raise XMLException(cant_read_xml_error)
        return self.xml_root

    def xml_parser_from_file(self, **kwargs):
        """
        :param kwargs: any another param
        :return: xml root element tree
        """
        try:
            self.tree = ElementTree.parse(self.xml_string, **kwargs)
        except XMLException:
            raise XMLException(cant_read_xml_error)
        self.xml_root = self.tree.getroot()
        self.xml_from_type = "file"
        return self.xml_root

    def write_xml(self, write_xml_filename: str, write_content: str):
        """
        :param write_xml_filename:  xml file name
        :param write_content: content to write
        """
        write_content = write_content.strip()
        content = self.element_tree.fromstring(write_content)
        tree = self.element_tree.ElementTree(content)
        tree.write(write_xml_filename, encoding="utf-8")
