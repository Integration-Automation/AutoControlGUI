AutoControl Critical Exit Doc
==========================

.. code-block:: python

   class CriticalExit(Thread):
    """
    use to make program interrupt
    """

        def __init__(self, default_daemon: bool = True):
            """
            default interrupt is keyboard F7 key
            :param default_daemon bool thread setDaemon
            """

        def set_critical_key(self, keycode: [int, str] = None):
            """
            set interrupt key
            :param keycode interrupt key
            """

          def run(self):
            """
            listener keycode _exit_check_key to interrupt
            """

         def init_critical_exit(self):
            """
            should only use this to start critical exit
            may this function will add more
            """
