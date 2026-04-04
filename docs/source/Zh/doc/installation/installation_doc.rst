======
安裝
======

從 PyPI 安裝
============

.. code-block:: bash

   pip install je_auto_control

系統需求
========

* Python 3.10 以上
* pip 19.3 以上

安裝 GUI 支援
=============

.. code-block:: bash

   pip install je_auto_control[gui]

Linux 前置套件
==============

.. code-block:: bash

   sudo apt-get install cmake libssl-dev

樹莓派
======

.. code-block:: bash

   sudo apt-get install python3
   pip3 install je_auto_control
   sudo apt-get install libcblas-dev libhdf5-dev libhdf5-serial-dev
   sudo apt-get install libatlas-base-dev libjasper-dev
   sudo apt-get install libqtgui4 libqt4-test
   pip3 install -U pillow numpy

開發環境
========

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 平台
     - 測試版本
   * - Windows
     - Windows 11
   * - macOS
     - macOS Big Sur (11)
   * - Linux
     - Ubuntu 20.04
   * - Raspberry Pi
     - 3B / 4B
