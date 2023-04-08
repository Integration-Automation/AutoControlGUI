Generate Report API
----

.. code-block:: python

    def generate_html() -> str:
        """
        this function will create html string
        :return: html_string
        """

.. code-block:: python

    def generate_html_report(html_name: str = "default_name"):
        """
        Output html report file
        :param html_name: save html file name
        """

.. code-block:: python

    def generate_json():
        """
        :return: two dict {success_dict}, {failure_dict}
        """

.. code-block:: python

    def generate_json_report(json_file_name: str = "default_name"):
        """
        Output json report file
        :param json_file_name: save json file's name
        """

.. code-block:: python

    def generate_xml():
        """
        :return: two dict {success_dict}, {failure_dict}
        """

.. code-block:: python

    def generate_xml_report(xml_file_name: str = "default_name"):
        """
        :param xml_file_name: save xml file name
        """