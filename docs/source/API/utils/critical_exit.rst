=================
Critical Exit API
=================

Safety mechanism to forcibly terminate automation scripts via a hotkey.

----

CriticalExit
============

.. class:: CriticalExit(default_daemon=True)

   A daemon thread that monitors a keyboard key and interrupts the main thread when pressed.
   Inherits from ``threading.Thread``.

   :param bool default_daemon: Whether the thread runs as a daemon. Defaults to ``True``.

   The default interrupt key is **F7**.

   .. method:: set_critical_key(keycode=None)

      Changes the hotkey used to trigger the critical exit.

      :param keycode: New key name or key code. If ``None``, no change is made.
      :type keycode: int or str

      **Example:**

      .. code-block:: python

         critical = CriticalExit()
         critical.set_critical_key("escape")

   .. method:: run()

      The thread's main loop. Continuously checks if the exit key is pressed and
      calls ``_thread.interrupt_main()`` when detected.

      .. warning:: Do not call ``run()`` directly. Use :meth:`init_critical_exit` instead.

   .. method:: init_critical_exit()

      Starts the critical exit monitoring thread. This is the recommended way to
      enable critical exit.

      **Example:**

      .. code-block:: python

         from je_auto_control import CriticalExit

         CriticalExit().init_critical_exit()
