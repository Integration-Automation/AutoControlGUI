"""Type-stub generator for the executor's ``AC_*`` command surface.

Run::

    python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi

to refresh the IDE-facing stub file.
"""
from je_auto_control.utils.stubs.generator import (
    StubSignature, collect_signatures, render_pyi, write_pyi,
)


__all__ = ["StubSignature", "collect_signatures", "render_pyi", "write_pyi"]
