"""Runtime language switcher + registry.

Languages are registered by a display name (shown in the menu) mapped to a
dict of key → translation. Missing keys fall through to the English default
so new features degrade gracefully before their translations land.
"""
from typing import Dict, List

from je_auto_control.gui.language_wrapper.english import english_word_dict
from je_auto_control.gui.language_wrapper.japanese import japanese_word_dict
from je_auto_control.gui.language_wrapper.simplified_chinese import (
    simplified_chinese_word_dict,
)
from je_auto_control.gui.language_wrapper.traditional_chinese import (
    traditional_chinese_word_dict,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


class LanguageWrapper:
    """Holds the active language and exposes lookups + change notifications."""

    def __init__(self) -> None:
        autocontrol_logger.info("Init LanguageWrapper")
        self._registry: Dict[str, dict] = {
            "English": english_word_dict,
            "Traditional_Chinese": traditional_chinese_word_dict,
            "Simplified_Chinese": simplified_chinese_word_dict,
            "Japanese": japanese_word_dict,
        }
        self.language: str = "English"
        self._listeners: List[callable] = []
        self.language_word_dict: dict = self._merged(self.language)

    @property
    def available_languages(self) -> List[str]:
        """Sorted list of registered language names."""
        return sorted(self._registry.keys())

    def register_language(self, name: str, words: dict) -> None:
        """Add or replace a language dict at runtime (plugin-friendly)."""
        self._registry[name] = dict(words)
        if name == self.language:
            self.language_word_dict = self._merged(name)

    def reset_language(self, language: str) -> None:
        if language not in self._registry:
            autocontrol_logger.warning("unknown language: %s", language)
            return
        self.language = language
        self.language_word_dict = self._merged(language)
        for listener in list(self._listeners):
            try:
                listener(language)
            except (OSError, RuntimeError) as error:
                autocontrol_logger.error("language listener failed: %r", error)

    def add_listener(self, callback) -> None:
        """Register ``callback(language)`` to fire when the language changes."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def translate(self, key: str, default: str = "") -> str:
        """Look up ``key`` in the active language, with English/default fallback."""
        value = self.language_word_dict.get(key)
        if value is not None:
            return value
        fallback = english_word_dict.get(key)
        if fallback is not None:
            return fallback
        return default or key

    def _merged(self, language: str) -> dict:
        merged = dict(english_word_dict)
        merged.update(self._registry.get(language, {}))
        return merged


language_wrapper = LanguageWrapper()
