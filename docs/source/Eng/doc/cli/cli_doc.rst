=======================
Command-Line Interface
=======================

AutoControl can be used directly from the command line to execute automation scripts.

Execute a Single Action File
=============================

.. code-block:: bash

   python -m je_auto_control --execute_file "path/to/actions.json"

   # Short form
   python -m je_auto_control -e "path/to/actions.json"

Execute All Files in a Directory
================================

.. code-block:: bash

   python -m je_auto_control --execute_dir "path/to/action_files/"

   # Short form
   python -m je_auto_control -d "path/to/action_files/"

Execute a JSON String Directly
==============================

.. code-block:: bash

   python -m je_auto_control --execute_str '[["AC_screenshot", {"file_path": "test.png"}]]'

Create a Project Template
=========================

.. code-block:: bash

   python -m je_auto_control --create_project "path/to/my_project"

   # Short form
   python -m je_auto_control -c "path/to/my_project"

Launch the GUI
==============

.. code-block:: bash

   python -m je_auto_control

.. note::

   Launching the GUI requires the ``[gui]`` extra to be installed:
   ``pip install je_auto_control[gui]``
