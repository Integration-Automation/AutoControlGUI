"""Declarative expected-outcome specs for an action, checked against the screen."""
from je_auto_control.utils.postcondition.postcondition import (
    PostconditionReport, check_postcondition, compile_postcondition,
)

__all__ = ["PostconditionReport", "check_postcondition", "compile_postcondition"]
