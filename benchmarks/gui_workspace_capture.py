"""Capture real Qt workspace layouts without invoking device or desktop operations."""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication  # pylint: disable=import-outside-toplevel  # reason: keep CLI parsing and helpers Qt-free
    from je_auto_control.gui.main_window import AutoControlGUIUI  # pylint: disable=import-outside-toplevel  # reason: keep CLI parsing and helpers Qt-free


def main() -> None:  # pylint: disable=too-many-locals  # reason: one render lifetime and environment report
    """Render dark English, light Chinese and small-window layouts with optional local fonts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', action='append', default=[])
    parser.add_argument('--tasks', action='store_true')
    args = parser.parse_args()
    from PySide6 import __version__ as qt_version  # pylint: disable=import-outside-toplevel  # reason: keep CLI parsing and helpers Qt-free
    from PySide6.QtGui import QFontDatabase, QFontInfo  # pylint: disable=import-outside-toplevel  # reason: keep CLI parsing and helpers Qt-free
    from PySide6.QtWidgets import QApplication  # pylint: disable=import-outside-toplevel  # reason: keep CLI parsing and helpers Qt-free
    # Keep CLI parsing and helpers Qt-free.
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import (  # pylint: disable=import-outside-toplevel
        language_wrapper,
    )
    from je_auto_control.gui.main_window import AutoControlGUIUI  # pylint: disable=import-outside-toplevel  # reason: keep CLI parsing and helpers Qt-free
    app = QApplication([])
    fonts = []
    for name in args.font:
        identifier = QFontDatabase.addApplicationFont(name)
        if identifier < 0:
            raise ValueError(f'could not load screenshot font: {name}')
        fonts.extend(QFontDatabase.applicationFontFamilies(identifier))
    if not QFontDatabase.families():
        raise ValueError('Qt has no fonts; provide installed fonts with --font for offscreen rendering')
    args.output.mkdir(parents=True, exist_ok=True)
    language_wrapper.reset_language('English')
    window = AutoControlGUIUI()
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    window.grab().save(str(args.output / 'dark-en.png'))
    window._set_theme(True)  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    language_wrapper.reset_language('Traditional_Chinese')
    window._apply_font_pt(14)  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    window.workspace_shell.navigation.search.setText('mobile')
    window.workspace_shell.navigation.open_key('mobile')
    app.processEvents()
    window.grab().save(str(args.output / 'light-zh-mobile.png'))
    window.resize(640, 480)
    app.processEvents()
    window.grab().save(str(args.output / 'small-zh-mobile.png'))
    small = {'small_window': [window.width(), window.height()],
             'small_workspace_width': window.workspace_shell.workspace_scroll.width()}
    task_states = _task_captures(window, app, args.output) if args.tasks else []
    report = {'platform': platform.platform(), 'python': platform.python_version(), 'pyside': qt_version,
              'qt_platform': app.platformName(), 'registered_font_families': sorted(set(fonts)),
              'resolved_font': QFontInfo(window.font()).family(), **small,
              'native_device_operations': False, 'task_states': task_states}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    window.close()
    app.processEvents()


def _task_captures(window: AutoControlGUIUI, app: QApplication, output: Path) -> list[str]:
    """Capture actual busy, cancelled and invalid-script task states without device I/O."""
    # Keep CLI parsing and helpers Qt-free.
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import (  # pylint: disable=import-outside-toplevel
        language_wrapper,
    )
    task_states = []
    window.resize(1280, 800)
    window._set_theme(False)  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    language_wrapper.reset_language('English')
    window.workspace_shell.navigation.search.setText('script')
    window.workspace_shell.navigation.open_key('script')
    widget = window.auto_control_gui_widget
    widget.script_editor.setPlainText('[["AC_sleep", {"seconds": 30}]]')
    widget._execute_manual_script()  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    app.processEvents()
    if window.workspace_shell.details.state != 'busy':
        raise ValueError('script did not present busy state')
    window.grab().save(str(output / 'busy-script.png'))
    task_states.append('busy')
    widget._cancel_script()  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    _pump(app, lambda: widget._script_tasks.handle is None)  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    window.grab().save(str(output / 'cancelled-script.png'))
    task_states.append(window.workspace_shell.details.state)
    widget.script_editor.setPlainText('{')
    widget._execute_manual_script()  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    _pump(app, lambda: widget._script_tasks.handle is None)  # pylint: disable=protected-access  # reason: exercise the real legacy GUI action
    if window.workspace_shell.details.state != 'error':
        raise ValueError('invalid JSON did not present error state')
    window.grab().save(str(output / 'error-script.png'))
    task_states.append('error')
    return task_states


def _pump(app: QApplication, predicate: Callable[[], bool]) -> None:
    """Allow real task completion before capture; timeout fails the artifact run."""
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    if not predicate():
        raise TimeoutError('task capture did not settle')


if __name__ == '__main__':
    main()
