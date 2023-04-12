創建專案
----

在 AutoControl 裡可以創建專案，創建專案後將會自動生成範例文件，
範例文件包含 python executor 檔案以及 keyword.json 檔案。

要創建專案可以用以下方式:

.. code-block:: python

    from je_auto_control import create_project_dir
    # create on current workdir
    create_project_dir()
    # create project on project_path
    create_project_dir("project_path")
    # create project on project_path and dir name is My First Project
    create_project_dir("project_path", "My First Project")

或是這個方式將會在 project_path 路徑產生專案

.. code-block:: console

    python -m je_auto_control --create_project project_path