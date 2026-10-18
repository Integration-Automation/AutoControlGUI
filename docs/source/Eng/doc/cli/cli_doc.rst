=======================
Command-Line Interface
=======================

Two CLI entry points are provided:

- ``python -m je_auto_control`` — legacy flag-style runner for one-off
  execute / create-project operations. Also launches the GUI when called
  with no arguments.
- ``python -m je_auto_control.cli`` — subcommand-based runner for running
  scripts, listing scheduler jobs, and starting the socket / REST servers.

Subcommand CLI (``python -m je_auto_control.cli``)
==================================================

Run a script
------------

.. code-block:: bash

   python -m je_auto_control.cli run script.json
   python -m je_auto_control.cli run script.json --var count=10 --var name=alice
   python -m je_auto_control.cli run script.json --dry-run
   python -m je_auto_control.cli run script.json --allow-package time --allow-package my_plugins

``--var name=value`` is parsed as JSON when the value parses, otherwise
it is treated as a plain string. ``--dry-run`` records every action
through the executor without invoking any side effects. Each invocation uses
an independent variable scope, with or without ``--var``; seeds and action-written
variables are discarded on success or error, including when called repeatedly
from the same Python process.

``--allow-package NAME`` (repeatable) puts a package, and its submodules, on
the package gate's allowlist for this run: ``AC_add_package_to_executor`` and
``AC_add_package_to_callback_executor`` refuse every package that has not
been allowed. The ``JE_AUTOCONTROL_ALLOWED_PACKAGES`` environment variable
(comma-separated names) does the same for every entry point, including the
legacy flags below, ``start-server``, ``start-rest`` and the MCP server.

Capture and inspect action journals
-----------------------------------

.. code-block:: bash

   python -m je_auto_control.cli run script.json --journal run.jsonl --journal-run-id example
   python -m je_auto_control.cli journal run.jsonl --run-id example --limit 100

``run --journal PATH`` appends structured lifecycle snapshots while preserving
the normal stdout record and action-failure exit code. It also supports
``--dry-run`` and ``--var``. Each capture generates a run ID unless
``--journal-run-id ID`` is supplied; that option requires ``--journal``.
No history row or database is created implicitly.

``journal PATH`` validates the entire file and prints a JSON array of sanitized
snapshots in append order. ``--run-id`` filters a run; ``--limit`` bounds output
to 1–10,000 snapshots (default 100), after filtering. Validation still reads the
whole file. Start and completion snapshots remain separate; incomplete entries
are never inferred successful. A missing file returns an empty array without
creating it. Malformed committed records fail before any JSON output.
Reading applies the journal's masking policy again and never changes the file.
Both journal paths use the existing allowed-root guard; configure
``AUTOCONTROL_ALLOWED_PATH_ROOTS`` for destinations outside the default roots.

List scheduler jobs
-------------------

.. code-block:: bash

   python -m je_auto_control.cli list-jobs

Start the TCP socket server
---------------------------

.. code-block:: bash

   python -m je_auto_control.cli start-server --host 127.0.0.1 --port 9938

Start the REST API server
-------------------------

.. code-block:: bash

   python -m je_auto_control.cli start-rest --host 127.0.0.1 --port 9939

Endpoints: ``GET /health``, ``GET /jobs``, ``POST /execute`` with
``{"actions": [...]}``.

Legacy flag-style CLI (``python -m je_auto_control``)
=====================================================

Execute a single action file
----------------------------

.. code-block:: bash

   python -m je_auto_control --execute_file "path/to/actions.json"
   python -m je_auto_control -e "path/to/actions.json"

Execute all files in a directory
--------------------------------

.. code-block:: bash

   python -m je_auto_control --execute_dir "path/to/action_files/"
   python -m je_auto_control -d "path/to/action_files/"

Every ``.json`` file under the directory runs, subdirectories included, in
sorted path order; links that lead outside the directory are not followed.

Execute a JSON string directly
------------------------------

.. code-block:: bash

   python -m je_auto_control --execute_str '[["AC_screenshot", {"file_path": "test.png"}]]'

Create a project template
-------------------------

.. code-block:: bash

   python -m je_auto_control --create_project "path/to/my_project"
   python -m je_auto_control -c "path/to/my_project"

Launch the GUI
--------------

.. code-block:: bash

   python -m je_auto_control

.. note::

   Launching the GUI requires the ``[gui]`` extra to be installed:
   ``pip install je_auto_control[gui]``
