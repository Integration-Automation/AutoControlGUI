from collections import defaultdict
from defusedxml import ElementTree as DefusedET  # nosec B405  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml  # reason: defusedxml is the safe replacement
from xml.etree import ElementTree  # nosec B405  # nosemgrep: python.lang.security.use-defused-xml.use-defused-xml  # reason: only used to construct trees, not to parse untrusted data
from typing import Any, Dict


def _initial_body(children: list, element: ElementTree.Element) -> Any:
    """Pick the starting body form: dict from children, empty dict, or None."""
    if children:
        return _children_to_dict(children)
    if element.attrib:
        return {}
    return None


def _children_to_dict(children: list) -> Dict[str, Any]:
    """Collapse children into ``{tag: value | [values]}`` form."""
    grouped: Dict[str, list] = defaultdict(list)
    for child_dict in (elements_tree_to_dict(c) for c in children):
        for key, value in child_dict.items():
            grouped[key].append(value)
    return {key: value[0] if len(value) == 1 else value
            for key, value in grouped.items()}


def _attach_attributes(element: ElementTree.Element,
                       body: Dict[str, Any]) -> None:
    """Merge ``element.attrib`` into ``body`` with ``@key`` prefixes."""
    if not element.attrib:
        return
    body.update(('@' + key, value) for key, value in element.attrib.items())


def _attach_text(element: ElementTree.Element,
                 elements_dict: Dict[str, Any],
                 has_structure: bool) -> None:
    """Attach text content using ``#text`` or as a flat string."""
    if not element.text:
        return
    text = element.text.strip()
    if has_structure:
        if text:
            elements_dict[element.tag]['#text'] = text
    else:
        elements_dict[element.tag] = text


def elements_tree_to_dict(elements_tree: ElementTree.Element) -> Dict[str, Any]:
    """
    Convert XML ElementTree to dictionary.
    將 XML ElementTree 轉換成 Python dict

    :param elements_tree: XML Element
    :return: dict representation of XML
    """
    children = list(elements_tree)
    body: Any = _initial_body(children, elements_tree)
    elements_dict: Dict[str, Any] = {elements_tree.tag: body}

    if isinstance(body, dict):
        _attach_attributes(elements_tree, body)

    has_structure = bool(children or elements_tree.attrib)
    _attach_text(elements_tree, elements_dict, has_structure)

    return elements_dict


def _validate_text_node(key: str, value: Any) -> None:
    if key != '#text' or not isinstance(value, str):
        raise ValueError(
            f"Invalid text node: key={key}, value type={type(value)}"
        )


def _set_attribute(root: ElementTree.Element, key: str, value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError(f"Expected str attribute value, got {type(value)}")
    root.set(key[1:], value)


def _build_child_node(parent: ElementTree.Element, key: str, value: Any) -> None:
    if isinstance(value, list):
        for element in value:
            _to_elements_tree(element, ElementTree.SubElement(parent, key))
    else:
        _to_elements_tree(value, ElementTree.SubElement(parent, key))


def _process_dict_entry(root: ElementTree.Element, key: str, value: Any) -> None:
    if not isinstance(key, str):
        raise TypeError(f"Expected str key, got {type(key)}")
    if key.startswith('#'):
        _validate_text_node(key, value)
        root.text = value
        return
    if key.startswith('@'):
        _set_attribute(root, key, value)
        return
    _build_child_node(root, key, value)


def _to_elements_tree(json_dict: Any, root: ElementTree.Element) -> None:
    if isinstance(json_dict, str):
        root.text = json_dict
        return
    if isinstance(json_dict, dict):
        for key, value in json_dict.items():
            _process_dict_entry(root, key, value)
        return
    raise TypeError(f"Invalid type: {type(json_dict)}")


def dict_to_elements_tree(json_dict: Dict[str, Any]) -> str:
    """
    Convert dictionary to XML string.
    將 Python dict 轉換成 XML 字串

    :param json_dict: dict representation of XML
    :return: XML string
    """
    if not isinstance(json_dict, dict) or len(json_dict) != 1:
        key_count = len(json_dict) if isinstance(json_dict, dict) else 'N/A'
        raise TypeError(
            f"Expected dict with exactly 1 key, got {type(json_dict)} "
            f"with {key_count} keys"
        )
    tag, body = next(iter(json_dict.items()))
    node = ElementTree.Element(tag)
    _to_elements_tree(body, node)
    return ElementTree.tostring(node, encoding="utf-8").decode("utf-8")


def parse_xml_string_safely(xml_string: str) -> ElementTree.Element:
    """Parse an XML string with defusedxml to avoid XXE / billion-laughs."""
    return DefusedET.fromstring(xml_string)
