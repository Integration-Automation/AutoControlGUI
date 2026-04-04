============
Installation
============

Install from PyPI
=================

.. code-block:: bash

   pip install je_auto_control

Requirements
============

* Python 3.10 or higher
* pip 19.3 or higher

With GUI Support
================

.. code-block:: bash

   pip install je_auto_control[gui]

Linux Prerequisites
===================

.. code-block:: bash

   sudo apt-get install cmake libssl-dev

Raspberry Pi
============

.. code-block:: bash

   sudo apt-get install python3
   pip3 install je_auto_control
   sudo apt-get install libcblas-dev libhdf5-dev libhdf5-serial-dev
   sudo apt-get install libatlas-base-dev libjasper-dev
   sudo apt-get install libqtgui4 libqt4-test
   pip3 install -U pillow numpy

Development Environment
=======================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Platform
     - Tested Version
   * - Windows
     - Windows 11
   * - macOS
     - macOS Big Sur (11)
   * - Linux
     - Ubuntu 20.04
   * - Raspberry Pi
     - 3B / 4B
