===========
AutoControl
===========

**AutoControl** is a cross-platform Python GUI automation framework providing mouse control,
keyboard input, image recognition, screen capture, action scripting, and report generation
-- all through a unified API that works on Windows, macOS, and Linux (X11).

.. note::

   AutoControl supports Linux Wayland via CLI bridges (wtype + ydotool +
   grim). See :doc:`getting_started/run_in_ci` for compositor / install
   notes. Set ``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11`` to force the
   XWayland fallback.

----

Getting Started
===============

.. toctree::
   :maxdepth: 2

   getting_started/installation
   getting_started/quickstart
   getting_started/run_in_ci

User Guide (English)
====================

.. toctree::
   :maxdepth: 2

   Eng/eng_index

User Guide (繁體中文)
=====================

.. toctree::
   :maxdepth: 2

   Zh/zh_index

API Reference
=============

.. toctree::
   :maxdepth: 2

   API/api_index

----

Links
=====

* `PyPI <https://pypi.org/project/je_auto_control/>`_
* `GitHub <https://github.com/Integration-Automation/AutoControlGUI>`_
* `Project Kanban <https://github.com/orgs/Integration-Automation/projects/2/views/1>`_

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
