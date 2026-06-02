"""Media Checks tab: audio activity and video motion assertions.

Thin wrapper over :func:`je_auto_control.assert_audio_activity` and
:func:`je_auto_control.assert_video_changes`.
"""
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
import je_auto_control as ac


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class MediaChecksTab(TranslatableMixin, QWidget):
    """Run a single audio or video media assertion and show the result."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._audio_duration = QDoubleSpinBox()
        self._audio_duration.setRange(0.1, 60.0)
        self._audio_duration.setValue(1.0)
        self._audio_threshold = QDoubleSpinBox()
        self._audio_threshold.setDecimals(4)
        self._audio_threshold.setRange(0.0, 1.0)
        self._audio_threshold.setValue(0.01)
        self._audio_expect = QCheckBox(_t("media_audio_expect"))
        self._audio_expect.setChecked(True)
        self._video_path = QLineEdit()
        self._video_threshold = QDoubleSpinBox()
        self._video_threshold.setRange(0.0, 255.0)
        self._video_threshold.setValue(1.0)
        self._video_expect = QCheckBox(_t("media_video_expect"))
        self._video_expect.setChecked(True)
        self._result = QLabel()
        self._result.setWordWrap(True)
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel(_t("media_audio_label")))
        arow = QHBoxLayout()
        arow.addWidget(QLabel(_t("media_audio_duration")))
        arow.addWidget(self._audio_duration)
        arow.addWidget(QLabel(_t("media_audio_threshold")))
        arow.addWidget(self._audio_threshold)
        arow.addWidget(self._audio_expect)
        audio_btn = self._tr(QPushButton(), "media_audio_run")
        audio_btn.clicked.connect(self._on_audio)
        arow.addWidget(audio_btn)
        arow.addStretch()
        root.addLayout(arow)

        root.addWidget(QLabel(_t("media_video_label")))
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel(_t("media_video_path")))
        vrow.addWidget(self._video_path, stretch=1)
        browse_btn = self._tr(QPushButton(), "media_video_browse")
        browse_btn.clicked.connect(self._on_browse)
        vrow.addWidget(browse_btn)
        root.addLayout(vrow)
        vrow2 = QHBoxLayout()
        vrow2.addWidget(QLabel(_t("media_video_threshold")))
        vrow2.addWidget(self._video_threshold)
        vrow2.addWidget(self._video_expect)
        video_btn = self._tr(QPushButton(), "media_video_run")
        video_btn.clicked.connect(self._on_video)
        vrow2.addWidget(video_btn)
        vrow2.addStretch()
        root.addLayout(vrow2)

        root.addWidget(self._result)
        root.addStretch()

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, _t("media_video_browse"))
        if path:
            self._video_path.setText(path)

    def _on_audio(self) -> None:
        try:
            result = ac.assert_audio_activity(
                duration_s=self._audio_duration.value(),
                threshold=self._audio_threshold.value(),
                expect_sound=self._audio_expect.isChecked(),
                raise_on_fail=False,
            )
        except (RuntimeError, OSError, ValueError) as error:
            self._result.setText(str(error))
            return
        self._result.setText(result.message)

    def _on_video(self) -> None:
        try:
            result = ac.assert_video_changes(
                self._video_path.text().strip(),
                threshold=self._video_threshold.value(),
                expect_motion=self._video_expect.isChecked(),
                raise_on_fail=False,
            )
        except (RuntimeError, OSError, ValueError, FileNotFoundError) as error:
            self._result.setText(str(error))
            return
        self._result.setText(result.message)
