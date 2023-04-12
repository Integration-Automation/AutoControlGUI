Create Project
----

In AutoControl, you can create a project which will automatically generate sample files once the project is created.
These sample files include a Python executor file and a keyword.json file.

To create a project, you can use the following method:

.. code-block:: python

    from je_auto_control import create_project_dir
    # create on current workdir
    create_project_dir()
    # create project on project_path
    create_project_dir("project_path")
    # create project on project_path and dir name is My First Project
    create_project_dir("project_path", "My First Project")

Or using CLI, this will generate a project at the project_path location.

.. code-block:: console

    python -m je_auto_control --create_project project_path