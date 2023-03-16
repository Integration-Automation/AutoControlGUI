from collections import defaultdict
from xml.etree import ElementTree


def elements_tree_to_dict(elements_tree):
    """
    :param elements_tree: full xml string
    :return: xml str to dict
    """
    elements_dict: dict = {elements_tree.tag: {} if elements_tree.attrib else None}
    children: list = list(elements_tree)
    if children:
        default_dict = defaultdict(list)
        for dc in map(elements_tree_to_dict, children):
            for key, value in dc.items():
                default_dict[key].append(value)
        elements_dict: dict = {
            elements_tree.tag: {key: value[0] if len(value) == 1 else value for key, value in default_dict.items()}}
    if elements_tree.attrib:
        elements_dict[elements_tree.tag].update(('@' + key, value) for key, value in elements_tree.attrib.items())
    if elements_tree.text:
        text = elements_tree.text.strip()
        if children or elements_tree.attrib:
            if text:
                elements_dict[elements_tree.tag]['#text'] = text
        else:
            elements_dict[elements_tree.tag] = text
    return elements_dict


def dict_to_elements_tree(json_dict: dict):
    """
    :param json_dict: json dict
    :return: json dict to xml string
    """

    def _to_elements_tree(json_dict: dict, root):
        if not json_dict:
            pass
        elif isinstance(json_dict, str):
            root.text = json_dict
        elif isinstance(json_dict, dict):
            for key, value in json_dict.items():
                assert isinstance(key, str)
                if key.startswith('#'):
                    assert key == '#text' and isinstance(value, str)
                    root.text = value
                elif key.startswith('@'):
                    assert isinstance(value, str)
                    root.set(key[1:], value)
                elif isinstance(value, list):
                    for elements in value:
                        _to_elements_tree(elements, ElementTree.SubElement(root, key))
                else:
                    _to_elements_tree(value, ElementTree.SubElement(root, key))
        else:
            raise TypeError('invalid type: ' + str(type(json_dict)))

    assert isinstance(json_dict, dict) and len(json_dict) == 1
    tag, body = next(iter(json_dict.items()))
    node = ElementTree.Element(tag)
    _to_elements_tree(body, node)
    return str(ElementTree.tostring(node), encoding="utf-8")
