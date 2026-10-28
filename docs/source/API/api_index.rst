=================
API Reference
=================

Complete API documentation for all AutoControl modules.

The root package resolves public exports when accessed. ``__all__`` and ``dir()``
list names without loading every feature; wildcard import resolves them all.
Unresolved exports are absent from ``vars(je_auto_control)``. Exported functions,
classes and shared objects retain their original identities.

Wrapper API
===========

Platform-agnostic high-level functions.

.. toctree::
   :maxdepth: 2

   wrapper/mouse
   wrapper/keyboard
   wrapper/image
   wrapper/screen
   wrapper/record

Utils API
=========

Utility modules for scripting, reporting, and more.

.. toctree::
   :maxdepth: 2

   utils/executor
   utils/callback
   utils/generate_report
   utils/scheduler
   utils/file
   utils/package_manager
   utils/socket_server
   utils/critical_exit

Key Reference
=============

Platform-specific key code tables.

.. toctree::
   :maxdepth: 2

   special/keyboard_keys
   special/mouse_keys
