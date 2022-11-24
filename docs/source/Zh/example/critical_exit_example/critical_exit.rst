====================================================
AutoControl Critical Exit
====================================================

| 緊急退出
| 如果需要在某些時候緊急退出可以使用此範例
| 當按下設定的退出鍵時將會退出程式
| 這個範例展示如何使用緊急退出

.. code-block:: python

    from je_auto_control import CriticalExit
    from je_auto_control import keys_table
    from je_auto_control import press_key
    try:
        """
        預設緊急退出鍵為F7
        """
        critical_exit_thread = CriticalExit()
        """
        可以設置為任何在 keys_table 裡的按鍵
        這裡設置為 F2
        """
        print(keys_table.keys())
        critical_exit_thread.set_critical_key("f2")
        """
        開始監聽 緊急退出鍵
        """
        critical_exit_thread.init_critical_exit()

        """
        這裡將會退出 當函數觸動系統模擬使用者按下F2
        """
        while True:
            press_key("f2")
    except KeyboardInterrupt:
        pass



