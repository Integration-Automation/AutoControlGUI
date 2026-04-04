==================
Project Management
==================

AutoControl can scaffold a project directory with template files to help you get started quickly.

Creating a Project
==================

Using Python:

.. code-block:: python

   from je_auto_control import create_project_dir

   # Create in current working directory
   create_project_dir()

   # Create at a specific path
   create_project_dir("path/to/project")

   # Create with a custom directory name
   create_project_dir("path/to/project", "My First Project")

Using the CLI:

.. code-block:: bash

   python -m je_auto_control --create_project "path/to/project"

Generated Structure
===================

.. code-block:: text

   my_project/
   └── AutoControl/
       ├── keyword/
       │   ├── keyword1.json          # Template action file
       │   ├── keyword2.json          # Template action file
       │   └── bad_keyword_1.json     # Error handling template
       └── executor/
           ├── executor_one_file.py   # Execute single file example
           ├── executor_folder.py     # Execute folder example
           └── executor_bad_file.py   # Error handling example

The ``keyword/`` directory contains JSON action files, and the ``executor/`` directory
contains Python scripts that demonstrate how to run them.
