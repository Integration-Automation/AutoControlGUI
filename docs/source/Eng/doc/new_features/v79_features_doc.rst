Dotenv (.env) Parsing
=====================

``script_vars.load_vars_from_json`` ingests flat JSON, but nothing read the
de-facto 12-factor ``.env`` file. This parses ``KEY=VALUE`` lines — honouring
``export`` prefixes, single/double quoting, escapes, and inline comments — into
a plain dict that can feed a config layer, with no ``python-dotenv`` dependency.

Pure standard library (``re``); imports no ``PySide6``. ``parse_dotenv`` is a
pure string-to-dict function, and the loader merges into a caller-supplied
mapping rather than mutating ``os.environ``, so it is safe and deterministic.

Headless API
------------

.. code-block:: python

    from je_auto_control import parse_dotenv, load_dotenv, dotenv_values, dump_dotenv

    values = parse_dotenv('PLAIN=hello\nexport TOKEN="a\\nb"  # comment')
    # {"PLAIN": "hello", "TOKEN": "a\nb"}

    config = {}
    load_dotenv(".env", config)                 # merge file into a dict
    load_dotenv(".env.local", config, override=True)

``parse_dotenv`` skips blanks and ``#`` comment lines, strips an optional
``export`` prefix, validates keys, and resolves values: single-quoted values
are literal, double-quoted values process ``\n`` / ``\t`` / ``\\`` / ``\"``
escapes, and unquoted values drop a trailing `` #`` comment and surrounding
whitespace. ``dotenv_values`` reads and parses a file; ``load_dotenv`` merges a
file into an explicit ``env`` mapping (keeping existing keys unless
``override``); ``dump_dotenv`` serialises a mapping back to ``.env`` text,
quoting values that need it.

Executor commands
-----------------

``AC_parse_dotenv`` parses ``text`` into ``{values}``; ``AC_load_dotenv`` reads
a file at ``path`` into a fresh ``{values}`` dict. Both are exposed as MCP tools
(``ac_parse_dotenv`` / ``ac_load_dotenv``) and as Script Builder commands under
**Data**.
