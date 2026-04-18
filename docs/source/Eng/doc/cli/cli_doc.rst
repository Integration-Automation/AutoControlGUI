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

``--var name=value`` is parsed as JSON when the value parses, otherwise
it is treated as a plain string. ``--dry-run`` records every action
through the executor without invoking any side effects.

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
