視窗 Z-order——置頂 / 移到最前 / 移到最後
=========================================

``windows_window_manage.set_window_position`` 在原始 Win32 層存在,但未在套件 facade 匯出、沒有以標題為基礎的包裝、
也沒有 topmost / not-topmost 語意——而 GUI 疊圖以外的地方完全沒有 ``always_on_top``。本功能加入標準 RPA z-order
基本能力:純函式 ``plan_zorder`` 將動作對應到 ``SetWindowPos`` 的 insert-after 常數,以及以標題操作、可注入 driver
的 ``set_topmost`` / ``bring_to_front`` / ``send_to_back``(與 ``snap_window`` 相同的接縫模式)。

規劃為純函式且可無頭測試;只有預設 driver 觸及 Win32(其他平台回傳 ``False``)。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (set_topmost, bring_to_front, send_to_back,
                                 plan_zorder)

    set_topmost("Media Player")          # 置頂
    set_topmost("Media Player", False)   # 取消置頂
    bring_to_front("Editor")
    send_to_back("Background Monitor")

    plan_zorder("topmost")["insert_after"]   # -1(HWND_TOPMOST),純 / 可測

``plan_zorder(action)``(``top`` / ``bottom`` / ``topmost`` / ``notopmost``)回傳 ``SetWindowPos`` 描述符
(``insert_after`` 常數 + ``SWP_NOMOVE`` / ``SWP_NOSIZE`` 旗標);未知動作丟出 ``ValueError``。``set_topmost`` /
``bring_to_front`` / ``send_to_back`` 以標題解析視窗並透過預設 Win32 driver(測試時注入)套用動作,回傳是否已套用。

執行器命令
----------

``AC_set_topmost``(``title`` / ``on`` → ``{applied}``)、``AC_bring_to_front`` 與 ``AC_send_to_back``
(``title`` → ``{applied}``)。它們以 MCP 工具 ``ac_set_topmost`` / ``ac_bring_to_front`` / ``ac_send_to_back``
以及 Script Builder 中 **Window** 分類下的命令提供。
