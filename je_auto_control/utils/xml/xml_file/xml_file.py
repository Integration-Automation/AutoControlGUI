"""Safe XML helpers backed by ``defusedxml``.

Direct ``xml.etree`` / ``xml.dom.minidom`` parsing is vulnerable to XXE and
billion-laughs attacks. We parse via ``defusedxml`` and only build trees with
the stdlib ``ElementTree`` (which is safe for construction).
"""
from defusedxml import ElementTree as DefusedET  # nosec B405  # reason: defusedxml is the safe replacement
from defusedxml.minidom import parseString as defused_parse_string
from xml.etree import ElementTree  # nosec B405  # reason: only used to construct trees, not parse untrusted data
from xml.etree.ElementTree import ParseError  # nosec B405  # reason: type used for catching, not for parsing

from je_auto_control.utils.exception.exception_tags import (
    cant_read_xml_error_message, xml_type_error_message,
)
from je_auto_control.utils.exception.exceptions import (
    XMLException, XMLTypeException,
)


def reformat_xml_file(xml_string: str) -> str:
    """
    Reformat XML string into pretty-printed format.
    將 XML 字串重新排版成漂亮格式

    :param xml_string: 原始 XML 字串 Raw XML string
    :return: 美化後的 XML 字串 Pretty XML string
    """
    dom = defused_parse_string(xml_string)
    return dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


class XMLParser:
    """
    XMLParser
    XML 解析器
    - 支援從字串或檔案載入 XML
    - 可輸出 XML 檔案
    """

    def __init__(self, xml_string: str, xml_type: str = "string"):
        """
        Initialize XMLParser.
        初始化 XMLParser

        :param xml_string: XML 字串或檔案路徑 XML string or file path
        :param xml_type: "string" 或 "file"
        """
        self.tree: ElementTree.ElementTree | None = None
        self.xml_root: ElementTree.Element | None = None
        self.xml_from_type: str = "string"
        self.xml_string: str = xml_string.strip()

        xml_type = xml_type.lower()
        if xml_type not in ["file", "string"]:
            raise XMLTypeException(xml_type_error_message)

        if xml_type == "string":
            self.xml_parser_from_string()
        else:
            self.xml_parser_from_file()

    def xml_parser_from_string(self, **kwargs) -> ElementTree.Element:
        """
        Parse XML from string.
        從字串解析 XML

        :return: XML root element
        """
        try:
            self.xml_root = DefusedET.fromstring(self.xml_string, **kwargs)
        except ParseError as error:
            raise XMLException(f"{cant_read_xml_error_message}: {repr(error)}") from error
        return self.xml_root

    def xml_parser_from_file(self, **kwargs) -> ElementTree.Element:
        """
        Parse XML from file.
        從檔案解析 XML

        :return: XML root element
        """
        try:
            self.tree = DefusedET.parse(self.xml_string, **kwargs)
        except (OSError, ParseError) as error:
            raise XMLException(f"{cant_read_xml_error_message}: {repr(error)}") from error
        self.xml_root = self.tree.getroot()
        self.xml_from_type = "file"
        return self.xml_root

    def write_xml(self, write_xml_filename: str, write_content: str) -> None:
        """
        Write XML content to file.
        將 XML 內容寫入檔案

        :param write_xml_filename: 輸出檔案名稱 Output file name
        :param write_content: XML 字串 XML string
        """
        try:
            content = DefusedET.fromstring(write_content.strip())
            tree = ElementTree.ElementTree(content)
            tree.write(write_xml_filename, encoding="utf-8", xml_declaration=True)
        except ParseError as error:
            raise XMLException(f"{cant_read_xml_error_message}: {repr(error)}") from error
