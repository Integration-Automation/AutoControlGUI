"""Classify what kind of widget a box is from its pixel shape."""
from je_auto_control.utils.icon_classify.icon_classify import (
    WIDGET_TYPES, box_features, classify_icon, classify_widget,
)

__all__ = ["classify_widget", "box_features", "classify_icon", "WIDGET_TYPES"]
