在動作群組中持續按住修飾鍵
==========================

``hotkey`` 按下一組鍵後立即放開——適合一次性的組合鍵,但先前無法在*多個獨立動作之間持續按住* ``ctrl``
(或 ``shift``)(以 shift 連點做範圍選取、以 ctrl 連點做多選),也無法確保即使其中某個動作拋例外時修飾鍵仍會
被放開。

:func:`plan_with_modifiers` 以 press / release 步驟包覆操作步驟清單,為純函式、可單元測試;:func:`hold_modifiers`
是一個 context manager,進入時按下、離開時(含例外情況)以反向順序放開,並透過可注入的 ``sink`` 派發。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import hold_modifiers, plan_with_modifiers
    from je_auto_control import click_mouse

    # 按住 shift 做範圍選取:每次點擊都在 shift 按下狀態進行
    with hold_modifiers(["shift"]):
        click_mouse("mouse_left", 100, 100)
        click_mouse("mouse_left", 100, 300)
    # shift 在此放開——即使某次點擊拋例外也是

    plan_with_modifiers([{"op": "click"}], ["ctrl", "shift"])
    # 按 ctrl、按 shift、click、放 shift、放 ctrl

修飾鍵進入時依序按下、離開時在 ``finally`` 區塊以*反向*順序放開,因此卡住的修飾鍵絕不會外洩。
``plan_with_modifiers`` 是任意操作步驟清單的純計畫。

執行器命令
----------

``AC_with_modifiers`` 在按住 ``modifiers``(如 ``["ctrl"]`` 或 ``"ctrl+shift"``)時執行巢狀 JSON 動作清單,
即使某動作失敗也會放開修飾鍵。它以 MCP 工具 ``ac_with_modifiers`` 以及 Script Builder 中 **Keyboard** 分類下
的命令提供。
