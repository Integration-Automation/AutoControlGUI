"""Text, config and registry defects from the 2026-09-24 audit (fakes only; no network, no screen).

"-or-later" licences were cut in three and slipped past a denylist; the
REST USB endpoints read "false" as true; .po entries without a blank line
between them (and every CRLF file) merged; -1 took the "other" plural and
large counts lost digits; a file URI naming another host read a local file;
a failing __repr__ broke a traced call; a newline in a coturn field added
directives; presence ids were stripped on register only and its errors
escaped the framework family; XML keys were written as raw markup.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.gettext_catalog.gettext_catalog import parse_po
from je_auto_control.utils.license_policy.license_policy import evaluate_license
from je_auto_control.utils.mcp_server._protocol import _file_uri_to_path
from je_auto_control.utils.message_format.message_format import format_message
from je_auto_control.utils.observability.tracing import Tracer, traced
from je_auto_control.utils.remote_desktop.presence import PresenceError, PresenceRegistry
from je_auto_control.utils.remote_desktop.turn_config import render_turnserver_conf
from je_auto_control.utils.rest_api import rest_handlers
from je_auto_control.utils.xml.change_xml_structure.change_xml_structure import dict_to_elements_tree


def test_or_later_licences_stay_whole():
    assert evaluate_license("GPL-3.0-or-later", deny=["GPL-3.0-or-later"]) == "denied"
    assert evaluate_license("GPL-2.0-or-later", allow=["GPL-2.0-or-later"]) == "allowed"
    assert evaluate_license("LicenseRef-Foo-And-Bar", allow=["LicenseRef-Foo-And-Bar"]) == "allowed"
    assert evaluate_license("(MIT OR Apache-2.0) AND Proprietary", allow=["MIT"]) == "denied"


def test_rest_usb_booleans_must_be_json_booleans(monkeypatch):
    from je_auto_control.utils.usb.passthrough import commands
    calls = []
    monkeypatch.setattr(commands, "passthrough_enable", lambda enabled: calls.append(enabled) or {})
    context = rest_handlers.RouteContext(query="", body={"enabled": "false"}, client_ip="127.0.0.1")
    status, _payload = rest_handlers.handle_usb_passthrough_enable(context)
    assert status == 400 and calls == []
    context = rest_handlers.RouteContext(
        query="", body={"vendor_id": "1234", "product_id": "abcd", "allow": "false"},
        client_ip="127.0.0.1")
    assert rest_handlers.handle_usb_acl_add(context)[0] == 400


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_po_entries_need_no_blank_line(newline):
    source = newline.join(['msgid ""', 'msgstr "Content-Type: text/plain; charset=UTF-8\\n"', "",
                           'msgid "a"', 'msgstr "A"', 'msgid "b"', 'msgstr "B"', ""])
    catalog = parse_po(source)
    assert catalog.gettext("a") == "A" and catalog.gettext("b") == "B"


def test_plural_categories_use_the_absolute_value():
    pattern = "{n, plural, one {# day} other {# days}}"
    assert format_message(pattern, {"n": -1}) == "-1 day"
    assert format_message("{n, selectordinal, one {#st} other {#th}}", {"n": -1}) == "-1st"
    assert format_message(pattern, {"n": 12345678901234567}) == "12345678901234567 days"


def test_a_file_uri_on_another_host_is_refused():
    assert _file_uri_to_path("file://server/share/x.txt") is None
    assert _file_uri_to_path("file://localhost/tmp/x.txt") is not None


def test_a_failing_repr_does_not_fail_the_traced_call():
    class _Bad:
        def __repr__(self):
            raise RuntimeError("repr boom")

    @traced(tracer=Tracer(force_noop=True), record_args=True)
    def work(value):
        return 7

    assert work(_Bad()) == 7


@pytest.mark.parametrize("field", ["realm", "user", "secret"])
def test_coturn_fields_cannot_add_directives(field):
    values = {"realm": "r", "user": "u", "secret": "s", field: "x\nallow-loopback-peers"}
    with pytest.raises(ValueError):
        render_turnserver_conf(listen_port=3478, tls_port=5349, **values)
    with pytest.raises(ValueError):
        render_turnserver_conf(realm="r", user="a:b", secret="s", listen_port=3478, tls_port=5349)


def test_presence_ids_errors_and_listeners():
    assert issubclass(PresenceError, AutoControlException)
    registry = PresenceRegistry()
    seen = []

    def broken(_viewer_id, _row):
        raise KeyError("listener bug")

    registry.add_listener(broken)
    registry.add_listener(lambda viewer_id, row: seen.append(viewer_id))
    registry.register(" v1 ", "Viewer")
    assert seen == ["v1"]
    assert registry.update_cursor(" v1 ", 3, 4).cursor_x == 3
    for bad in (lambda: registry.update_cursor("v1", float("nan"), 0),
                lambda: registry.register("v2", "x", role=1)):
        with pytest.raises(PresenceError):
            bad()
    assert registry.unregister(" v1 ") is True


@pytest.mark.parametrize("document", [
    {"a": {"b><evil x='1'/><c": "t"}},
    {"a": {"@x=\"1\" onload": "v"}},
    {"a b": "t"},
])
def test_xml_names_are_validated(document):
    with pytest.raises(ValueError):
        dict_to_elements_tree(document)


def test_valid_xml_names_still_convert():
    assert dict_to_elements_tree({"ns:root": {"@id": "1", "child-1": "x"}}) == \
        '<ns:root id="1"><child-1>x</child-1></ns:root>'
