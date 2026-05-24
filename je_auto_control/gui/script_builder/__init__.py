"""Visual script editor for composing AC_* action lists.

``ScriptBuilderTab`` pulls in PySide6, so it loads lazily through
:func:`__getattr__`. Submodules such as :mod:`step_model` are Qt-free
and can be imported directly from headless tests::

    from je_auto_control.gui.script_builder.step_model import Step
"""


def __getattr__(name):
    if name == "ScriptBuilderTab":
        import importlib
        module = importlib.import_module(
            "je_auto_control.gui.script_builder.builder_tab",
        )
        return module.ScriptBuilderTab
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ScriptBuilderTab"]
