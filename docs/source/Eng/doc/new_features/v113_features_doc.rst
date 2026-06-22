ICU-lite MessageFormat (Plural / Select)
========================================

``i18n_test.check_catalog`` only compares placeholder *sets* and ``interpolate``
does flat ``${var}`` substitution — neither can render the count-aware messages
real localisation needs, e.g. ``"{count, plural, one {# item} other {# items}}"``.
This implements the ICU MessageFormat subset most apps use.

Pure standard library; imports no ``PySide6``. The plural/ordinal category
functions are pure and the rule callables are injectable, so rendering is fully
deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import format_message, plural_category, ordinal_category

    plural = "{count, plural, one {# item} other {# items}}"
    format_message(plural, {"count": 1})       # '1 item'
    format_message(plural, {"count": 5})       # '5 items'

    select = "{g, select, male {He} female {She} other {They}} won"
    format_message(select, {"g": "female"})    # 'She won'

    ordinal = "{place, selectordinal, one {#st} two {#nd} few {#rd} other {#th}}"
    format_message(ordinal, {"place": 3})      # '3rd'

    plural_category(2)                         # 'other'
    ordinal_category(3)                        # 'few'

Supported: simple ``{name}`` arguments, ``select`` (e.g. gender), ``plural`` and
``selectordinal`` with the CLDR categories (``zero``/``one``/``two``/``few``/
``many``/``other``), exact ``=N`` selectors that win over a category, the ``#``
count placeholder, a plural ``offset:`` (``#`` becomes count − offset), nested
arguments, and ICU apostrophe quoting (``''`` → ``'``; ``'{'`` → literal brace).
``plural_rules`` / ``ordinal_rules`` let you inject custom category functions;
``locale`` selects the built-ins (``en``, ``fr``).

Executor commands
-----------------

``AC_format_message`` takes a ``pattern`` plus a JSON ``args`` object and returns
``{text}``, accepting ``locale``. It is exposed as the MCP tool
``ac_format_message`` and as a Script Builder command under **Data**.
