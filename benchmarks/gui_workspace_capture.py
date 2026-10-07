"""Capture real Qt workspace layouts without invoking device or desktop operations."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path


def main() -> None:
    """Render dark English, light Chinese and small-window layouts with optional local fonts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', action='append', default=[])
    args = parser.parse_args()
    from PySide6 import __version__ as qt_version
    from PySide6.QtGui import QFontDatabase, QFontInfo
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    from je_auto_control.gui.main_window import AutoControlGUIUI
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
    window._set_theme(True)
    language_wrapper.reset_language('Traditional_Chinese')
    window._apply_font_pt(14)
    window.workspace_shell.navigation.search.setText('mobile')
    window.workspace_shell.navigation.open_key('mobile')
    app.processEvents()
    window.grab().save(str(args.output / 'light-zh-mobile.png'))
    window.resize(640, 480)
    app.processEvents()
    window.grab().save(str(args.output / 'small-zh-mobile.png'))
    report = {'platform': platform.platform(), 'python': platform.python_version(), 'pyside': qt_version,
              'qt_platform': app.platformName(), 'registered_font_families': sorted(set(fonts)),
              'resolved_font': QFontInfo(window.font()).family(), 'small_window': [window.width(), window.height()],
              'small_workspace_width': window.workspace_shell.workspace_scroll.width(),
              'native_device_operations': False}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    window.close()
    app.processEvents()


if __name__ == '__main__':
    main()
