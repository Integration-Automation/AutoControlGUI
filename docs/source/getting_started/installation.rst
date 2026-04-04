============
Installation
============

Requirements
============

* **Python** >= 3.10
* **pip** >= 19.3

Basic Installation
==================

Install AutoControl from PyPI:

.. code-block:: bash

   pip install je_auto_control

With GUI Support
================

To use the built-in PySide6 graphical interface:

.. code-block:: bash

   pip install je_auto_control[gui]

Linux Prerequisites
===================

On Linux, install the following system packages **before** installing AutoControl:

.. code-block:: bash

   sudo apt-get install cmake libssl-dev

Raspberry Pi
============

On Raspberry Pi (3B / 4B), install the following:

.. code-block:: bash

   sudo apt-get install python3
   pip3 install je_auto_control
   sudo apt-get install libcblas-dev libhdf5-dev libhdf5-serial-dev
   sudo apt-get install libatlas-base-dev libjasper-dev
   sudo apt-get install libqtgui4 libqt4-test
   pip3 install -U pillow numpy

Dependencies
============

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Package
     - Purpose
   * - ``je_open_cv``
     - Image recognition (OpenCV template matching)
   * - ``pillow``
     - Screenshot capture
   * - ``mss``
     - Fast multi-monitor screenshot
   * - ``pyobjc``
     - macOS backend (auto-installed on macOS)
   * - ``python-Xlib``
     - Linux X11 backend (auto-installed on Linux)
   * - ``PySide6``
     - GUI application (optional, install with ``[gui]``)
   * - ``qt-material``
     - GUI theme (optional, install with ``[gui]``)

Platform Support
================

.. list-table::
   :header-rows: 1
   :widths: 20 15 25 40

   * - Platform
     - Status
     - Backend
     - Notes
   * - Windows 10 / 11
     - Supported
     - Win32 API (ctypes)
     - Full feature support
   * - macOS 10.15+
     - Supported
     - pyobjc / Quartz
     - Action recording not available; ``send_key_event_to_window`` / ``send_mouse_event_to_window`` not supported
   * - Linux (X11)
     - Supported
     - python-Xlib
     - Full feature support
   * - Linux (Wayland)
     - Not supported
     - --
     - May be added in a future release
   * - Raspberry Pi 3B / 4B
     - Supported
     - python-Xlib
     - Runs on X11
