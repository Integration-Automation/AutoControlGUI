=================
Report Generation
=================

AutoControl can generate test reports in HTML, JSON, and XML formats. Reports record
which automation steps were executed and whether they succeeded or failed.

Setup
=====

Before generating reports, enable test recording:

.. code-block:: python

   from je_auto_control import test_record_instance

   test_record_instance.init_record = True

.. important::

   Recording must be enabled **before** executing actions, otherwise no data will be captured.

Generating Reports
==================

HTML Report
-----------

.. code-block:: python

   from je_auto_control import execute_action, generate_html_report, test_record_instance

   test_record_instance.init_record = True

   actions = [
       ["set_record_enable", {"set_enable": True}],
       ["AC_set_mouse_position", {"x": 500, "y": 500}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
       ["generate_html_report"],
   ]
   execute_action(actions)

This produces an HTML file where successful actions appear in **cyan** and failed actions in **red**.

JSON Report
-----------

.. code-block:: python

   from je_auto_control import generate_json_report

   generate_json_report("test_report")  # -> test_report.json

XML Report
----------

.. code-block:: python

   from je_auto_control import generate_xml_report

   generate_xml_report("test_report")  # -> test_report.xml

Getting Report Content as String
================================

If you need the report content without saving to a file:

.. code-block:: python

   from je_auto_control import generate_html, generate_json, generate_xml

   html_string = generate_html()
   json_data = generate_json()
   xml_data = generate_xml()

Report Contents
===============

Each report entry includes:

* **Function name** -- the automation function that was called
* **Parameters** -- the arguments passed to the function
* **Timestamp** -- when the action was executed
* **Exception info** -- error details if the action failed
