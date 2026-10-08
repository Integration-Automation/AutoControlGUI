"""The Diagnostics tab shows capability states, in every language."""
import os

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui import diagnostics_tab as tab_mod  # noqa: E402
from je_auto_control.gui.language_wrapper.english import (  # noqa: E402
    english_word_dict,
)
from je_auto_control.gui.language_wrapper.japanese import (  # noqa: E402
    japanese_word_dict,
)
from je_auto_control.gui.language_wrapper.simplified_chinese import (  # noqa: E402
    simplified_chinese_word_dict,
)
from je_auto_control.gui.language_wrapper.traditional_chinese import (  # noqa: E402
    traditional_chinese_word_dict,
)
from je_auto_control.linux_wayland import authorisation as auth  # noqa: E402
from je_auto_control.utils.diagnostics.diagnostics import (  # noqa: E402
    DiagnosticsReport,
)
from je_auto_control.wrapper import capabilities as caps  # noqa: E402

_CATALOGUES = {
    "english": english_word_dict, "japanese": japanese_word_dict,
    "simplified_chinese": simplified_chinese_word_dict,
    "traditional_chinese": traditional_chinese_word_dict,
}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _declined_wayland():
    ledger = auth.AuthorisationLedger()
    ledger.transition(auth.INPUT, auth.AuthorisationState.DECLINED,
                      "Portal denied Start")
    return caps.probe_capabilities(caps.BackendContext(
        platform="linux",
        environ={"XDG_SESSION_TYPE": "wayland"},
        which=lambda name: None, library_present=lambda _name: True,
        session_bus_present=lambda: False, readable=lambda _path: False,
        compositor=lambda _env: None, authorisations=ledger))


def test_every_state_and_every_fix_is_in_all_four_catalogues():
    """A state with no translation would show its raw key to the user."""
    source = open(caps.__file__, encoding="utf-8").read()
    wanted = {f"cap_state_{state.value}" for state in caps.CapabilityStatus}
    wanted |= {f"cap_name_{name}" for name in (
        caps.INPUT, caps.CAPTURE, caps.RECORDING, caps.STOP_SHORTCUT)}
    wanted |= {key for key in english_word_dict
               if key.startswith("cap_fix_")}
    wanted |= set(tab_mod._CAPABILITY_COLUMNS)
    wanted |= {"cap_scope_desktop", "cap_scope_xwayland",
               "diag_capabilities_title", "diag_capabilities_refresh",
               "diag_input_reask", "diag_input_close"}
    for language, catalogue in _CATALOGUES.items():
        missing = sorted(key for key in wanted if not catalogue.get(key))
        assert missing == [], f"{language} lacks {missing}"
    # Every advice key the headless module names exists, and none is unused.
    for key in (k for k in english_word_dict if k.startswith("cap_fix_")):
        assert f'"{key}"' in source, f"{key} is not used by capabilities.py"


def test_the_tab_shows_states_with_actionable_text(app, monkeypatch):
    monkeypatch.setattr(tab_mod, "run_diagnostics",
                        lambda: DiagnosticsReport(checks=[]))
    monkeypatch.setattr(tab_mod, "probe_capabilities", _declined_wayland)
    tab = tab_mod.DiagnosticsTab()

    table = tab._capabilities
    assert table.rowCount() == 4
    row = {table.horizontalHeaderItem(col).text(): table.item(0, col).text()
           for col in range(table.columnCount())}
    assert row[tab_mod._t("diag_cap_col_state")] == tab_mod._t(
        "cap_state_needs_permission")
    assert row[tab_mod._t("diag_cap_col_backend")] == "libei"
    assert row[tab_mod._t("diag_cap_col_detail")] == "Portal denied Start"
    assert row[tab_mod._t("diag_cap_col_fix")] == tab_mod._t(
        "cap_fix_input_consent")
    # Every row that is not usable says what to do.
    for index, capability in enumerate(_declined_wayland().capabilities):
        if capability.state is not caps.CapabilityStatus.AVAILABLE:
            assert table.item(index, 5).text(), capability.name


def test_the_tab_commands_live_in_the_actions_menu(app, monkeypatch):
    monkeypatch.setattr(tab_mod, "run_diagnostics",
                        lambda: DiagnosticsReport(checks=[]))
    calls = []
    monkeypatch.setattr(tab_mod, "reset_input_authorisation",
                        lambda: calls.append("reset"))
    monkeypatch.setattr(tab_mod, "close_input_session",
                        lambda: calls.append("close"))
    tab = tab_mod.DiagnosticsTab()
    actions = dict(tab.menu_actions())
    assert list(actions) == ["diag_run", "diag_capabilities_refresh",
                             "diag_input_reask", "diag_input_close"]
    actions["diag_input_reask"]()
    actions["diag_input_close"]()
    actions["diag_capabilities_refresh"]()
    assert calls == ["reset", "close"]
    tab.retranslate()
    assert tab._capabilities.rowCount() == 4


def test_xwayland_is_shown_as_a_narrower_scope():
    snapshot = caps.probe_capabilities(caps.BackendContext(
        platform="linux", loaded_backend="x11",
        environ={"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}))
    cells = tab_mod.capability_cells(snapshot.input)
    assert cells[3] == tab_mod._t("cap_scope_xwayland")
    assert cells[5] == tab_mod._t("cap_fix_xwayland")
