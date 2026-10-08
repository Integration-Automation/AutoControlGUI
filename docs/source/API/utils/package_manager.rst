====================
Package Manager API
====================

The ``PackageManager`` class dynamically loads external Python packages into the
executor and callback executor at runtime.

----

PackageManager
==============

.. class:: PackageManager

   .. method:: check_package(package)

      Checks if a package is installed and importable.

      :param str package: Package name to check.
      :returns: The imported module if found, ``None`` otherwise.

   .. method:: add_package_to_executor(package)

      Loads all functions, built-ins, and classes from a package into the main executor's
      ``event_dict``.

      :param str package: Package name to load.
      :raises AutoControlExecuteActionException: the package gate refused the package
         (see ``allow_packages``); nothing is imported.

      Functions are added with the naming convention ``package_function``.
      For example, ``time.sleep`` becomes ``time_sleep``.

   .. method:: add_package_to_callback_executor(package)

      Loads all functions, built-ins, and classes from a package into the callback executor's
      ``event_dict``.

      :param str package: Package name to load.

   .. method:: get_member(package, predicate, target)

      Retrieves members from a package matching the given predicate and adds them to the
      target executor.

      :param str package: Package name.
      :param predicate: Inspection predicate (e.g., ``isfunction``, ``isclass``).
      :param target: Target executor whose ``event_dict`` will be updated.

   .. method:: allow_packages(*packages)

      Adds packages, and their submodules, to the package gate's allowlist. The allowlist starts
      from the comma-separated names in the ``JE_AUTOCONTROL_ALLOWED_PACKAGES`` environment
      variable, read when the manager is created; ``je_auto_control run --allow-package NAME``
      adds to it for one run. Raises ``AutoControlExecuteActionException`` for a name that is not
      a dotted module name.

   .. method:: set_allow_arbitrary_packages(enabled)

      Allows (``True``) or refuses (``False``, the default) packages outside the allowlist.
      ``add_package_to_executor`` and ``add_package_to_callback_executor`` check the gate before
      importing and raise ``AutoControlExecuteActionException`` for a refused package, so with
      nothing configured no package loads. The ``Executor`` has the same two static methods;
      neither is an ``AC_*`` command.

   .. method:: add_package_to_target(package, target)

      Loads functions, built-ins, and classes from a package into the specified target executor.

      :param str package: Package name.
      :param target: Target executor.

**Example:**

.. code-block:: python

   from je_auto_control import package_manager

   # Nothing loads until it is allowed (the package gate)
   package_manager.allow_packages("os")

   # Add 'os' module to the executor
   package_manager.add_package_to_executor("os")

   # Now you can use os functions in JSON actions:
   # ["os_getcwd", {}]
   # ["os_listdir", {"path": "."}]
