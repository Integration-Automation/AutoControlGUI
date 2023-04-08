Executor API
----

.. code-block:: python

    def execute_action(self, action_list: [list, dict]) -> dict:
        """
        use to execute all action on action list(action file or program list)
        :param action_list the list include action
        for loop the list and execute action
        """

.. code-block:: python

    def execute_files(self, execute_files_list: list) -> list:
        """
        :param execute_files_list: list include execute files path
        :return: every execute detail as list
        """

.. code-block:: python

    def add_command_to_executor(command_dict: dict):
        """
        :param command_dict: dict include command we want to add to event_dict
        """