"""OCR Reader tab: dump text in a region, or regex-search for matches."""
import json
import re
from typing import Optional

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.selector import open_region_selector
from je_auto_control.utils.ocr.ocr_engine import (
    find_text_regex, read_text_in_region,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _matches_to_json(matches) -> str:
    rows = [
        {
            "text": m.text, "x": m.x, "y": m.y,
            "width": m.width, "height": m.height,
            "confidence": m.confidence,
        }
        for m in matches
    ]
    return json.dumps(rows, indent=2, ensure_ascii=False)


class OCRReaderTab(TranslatableMixin, QWidget):
    """Drive headless OCR helpers (region dump + regex search) from the UI."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._region = QLineEdit()
        self._lang = QLineEdit("eng")
        self._min_conf = QLineEdit("60")
        self._regex = QLineEdit()
        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._status = QLabel()
        self._apply_placeholders()
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()

    def _apply_placeholders(self) -> None:
        self._region.setPlaceholderText(_t("ocr_region_placeholder"))
        self._regex.setPlaceholderText(_t("ocr_regex_placeholder"))

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        region_group = self._tr(QGroupBox(), "ocr_region_group")
        region_layout = QHBoxLayout()
        region_layout.addWidget(self._tr(QLabel(), "ocr_region_label"))
        region_layout.addWidget(self._region, stretch=1)
        pick_btn = self._tr(QPushButton(), "ocr_pick_region")
        pick_btn.clicked.connect(self._on_pick_region)
        region_layout.addWidget(pick_btn)
        region_group.setLayout(region_layout)
        root.addWidget(region_group)

        params_layout = QHBoxLayout()
        params_layout.addWidget(self._tr(QLabel(), "ocr_lang_label"))
        params_layout.addWidget(self._lang)
        params_layout.addWidget(self._tr(QLabel(), "ocr_min_conf_label"))
        params_layout.addWidget(self._min_conf)
        params_layout.addStretch()
        root.addLayout(params_layout)

        regex_layout = QHBoxLayout()
        regex_layout.addWidget(self._tr(QLabel(), "ocr_regex_label"))
        regex_layout.addWidget(self._regex, stretch=1)
        root.addLayout(regex_layout)

        btn_row = QHBoxLayout()
        dump_btn = self._tr(QPushButton(), "ocr_dump_region")
        dump_btn.clicked.connect(self._on_dump)
        find_btn = self._tr(QPushButton(), "ocr_find_regex")
        find_btn.clicked.connect(self._on_find_regex)
        btn_row.addWidget(dump_btn)
        btn_row.addWidget(find_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addWidget(self._tr(QLabel(), "ocr_results_label"))
        root.addWidget(self._result, stretch=1)
        root.addWidget(self._status)

    def _on_pick_region(self) -> None:
        region = open_region_selector(self)
        if region is None:
            return
        x, y, width, height = region
        self._region.setText(f"{x}, {y}, {width}, {height}")

    def _parse_region(self) -> Optional[list]:
        text = self._region.text().strip()
        if not text:
            return None
        try:
            parts = [int(token.strip()) for token in text.split(",")]
        except ValueError as error:
            raise ValueError(_t("ocr_region_invalid")) from error
        if len(parts) != 4:
            raise ValueError(_t("ocr_region_invalid"))
        return parts

    def _parse_min_conf(self) -> float:
        text = self._min_conf.text().strip() or "0"
        try:
            return float(text)
        except ValueError as error:
            raise ValueError(_t("ocr_min_conf_invalid")) from error

    def _on_dump(self) -> None:
        try:
            region = self._parse_region()
            min_conf = self._parse_min_conf()
            lang = self._lang.text().strip() or "eng"
            matches = read_text_in_region(
                region=region, lang=lang, min_confidence=min_conf,
            )
        except ValueError as error:
            self._status.setText(str(error))
            return
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(self, _t("ocr_dump_region"), str(error))
            return
        self._result.setText(_matches_to_json(matches))
        self._status.setText(
            _t("ocr_match_count").replace("{n}", str(len(matches)))
        )

    def _on_find_regex(self) -> None:
        pattern = self._regex.text().strip()
        if not pattern:
            self._status.setText(_t("ocr_regex_required"))
            return
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            self._status.setText(f"{_t('ocr_regex_invalid')}: {error}")
            return
        try:
            region = self._parse_region()
            min_conf = self._parse_min_conf()
            lang = self._lang.text().strip() or "eng"
            matches = find_text_regex(
                compiled, lang=lang, region=region, min_confidence=min_conf,
            )
        except ValueError as error:
            self._status.setText(str(error))
            return
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(self, _t("ocr_find_regex"), str(error))
            return
        self._result.setText(_matches_to_json(matches))
        self._status.setText(
            _t("ocr_match_count").replace("{n}", str(len(matches)))
        )
