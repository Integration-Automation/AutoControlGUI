"""Type arbitrary Unicode (emoji / CJK / accented) by key injection or clipboard."""
from je_auto_control.utils.text_unicode.text_unicode import (
    plan_paste, plan_unicode_keys, type_unicode, type_unicode_keys,
    type_unicode_text, unicode_code_units, unicode_keys_supported,
)

__all__ = ["plan_paste", "plan_unicode_keys", "type_unicode",
           "type_unicode_keys", "type_unicode_text", "unicode_code_units",
           "unicode_keys_supported"]
