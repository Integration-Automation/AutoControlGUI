=====================
Report Generation API
=====================

Functions for generating test reports from recorded automation actions.

----

generate_html
=============

.. function:: generate_html()

   Creates an HTML string from recorded test actions.

   :returns: HTML report content.
   :rtype: str

----

generate_html_report
====================

.. function:: generate_html_report(html_name="default_name")

   Saves an HTML report file.

   :param str html_name: Output file name (without extension).

----

generate_json
=============

.. function:: generate_json()

   Creates JSON data from recorded test actions.

   :returns: Tuple of ``(success_dict, failure_dict)``.
   :rtype: tuple[dict, dict]

----

generate_json_report
====================

.. function:: generate_json_report(json_file_name="default_name")

   Saves a JSON report file.

   :param str json_file_name: Output file name (without extension).

----

generate_xml
============

.. function:: generate_xml()

   Creates XML data from recorded test actions.

   :returns: Tuple of ``(success_dict, failure_dict)``.
   :rtype: tuple[dict, dict]

----

generate_xml_report
===================

.. function:: generate_xml_report(xml_file_name="default_name")

   Saves an XML report file.

   :param str xml_file_name: Output file name (without extension).
