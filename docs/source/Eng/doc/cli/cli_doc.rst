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
through the executor without invoking any side effects.

``--allow-package NAME`` (repeatable) puts a package, and its submodules, on
the package gate's allowlist for this run: ``AC_add_package_to_executor`` and
``AC_add_package_to_callback_executor`` refuse every package that has not
been allowed. The ``JE_AUTOCONTROL_ALLOWED_PACKAGES`` environment variable
(comma-separated names) does the same for every entry point, including the
legacy flags below, ``start-server``, ``start-rest`` and the MCP server.

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

Manage RBAC users
-----------------

.. code-block:: bash

   python -m je_auto_control.cli users --users users.json add alice --role admin
   python -m je_auto_control.cli users --users users.json list
   python -m je_auto_control.cli users --users users.json set-role bob operator
   python -m je_auto_control.cli users --users users.json rotate-token bob
   python -m je_auto_control.cli users --users users.json remove bob

The users of the REST API and MCP server when RBAC is on (see *Roles* in the
operations-layer chapter). ``--users`` names the store file and defaults to
``JE_AUTOCONTROL_RBAC_USERS``; ``--json`` (before the sub-command) prints the
result as JSON. ``add`` (``--role viewer|operator|admin``, ``--name``,
``--tag``) and ``rotate-token`` print the token once -- it is not stored and
cannot be shown again. The last admin cannot be removed or demoted;
``remove`` exits 1 when there is no such user. ``python -m
je_auto_control.utils.rbac`` takes the same arguments without the leading
``users``.

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
