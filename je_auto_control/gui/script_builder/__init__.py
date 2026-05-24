"""Visual script editor for composing AC_* action lists.

``ScriptBuilderTab`` pulls in PySide6, so it loads lazily through
:func:`__getattr__`. Submodules such as :mod:`step_model` are Qt-free
and can be imported directly from headless tests::

    from je_auto_control.gui.script_builder.step_model import Step

``__all__`` is empty on purpose: Pylint's E0603 refuses to certify
``ScriptBuilderTab`` because it is not bound at module-load time.
Callers reach the tab via attribute access, which falls through to
:func:`__getattr__` and loads the Qt submodule on demand.
"""


def __getattr__(name):
    if name == "ScriptBuilderTab":
        import importlib
        module = importlib.import_module(
            "je_auto_control.gui.script_builder.builder_tab",
        )
        return module.ScriptBuilderTab
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__: list[str] = []
