"""Reactive screen observer — fire on appear / vanish / change."""
from je_auto_control.utils.observer.observer import (
    EVENT_APPEAR, EVENT_CHANGE, EVENT_VANISH,
    ScreenObserver, WatchRule, default_observer,
    image_predicate, pixel_predicate, text_predicate,
)

__all__ = [
    "EVENT_APPEAR", "EVENT_CHANGE", "EVENT_VANISH",
    "ScreenObserver", "WatchRule", "default_observer",
    "image_predicate", "pixel_predicate", "text_predicate",
]
