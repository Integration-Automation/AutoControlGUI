AutoControl 緊急退出 文件
==========================

.. code-block:: python

   class CriticalExit(Thread):
        "當程式需要緊急退出時可使用此類別"

        def __init__(self, default_daemon: bool = True):
            """
            預設使用鍵盤 F7 來緊急中斷
            是否隨著主程式關閉監聽 預設 True
            :param default_daemon bool thread setDaemon
            """

        def set_critical_key(self, keycode: [int, str] = None):
            """
            設置中斷按鈕用
            :param keycode interrupt key
            """

          def run(self):
            """
            本質上還是thread
            listener keycode _exit_check_key to interrupt
            """

         def init_critical_exit(self):
            """
            應該使用這方法開始監聽而不是原始 thread start
            should only use this to start critical exit
            may this function will add more
            """
