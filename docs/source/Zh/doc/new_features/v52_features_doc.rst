Saga / 補償回溯
===============

有些自動化橫跨數個看似不可逆的步驟 —— 建立紀錄、寄送郵件、移動檔案。若後續步驟失敗,
已完成的步驟應被**復原**,但執行器的 ``AC_try`` 只對單一區塊做 try/catch/finally;沒有
任何機制追蹤跨 N 個已完成步驟「該復原什麼」。``Saga`` 為每個步驟記錄一個補償動作,並在
任何失敗時以 **LIFO** 順序對已完成步驟執行補償。

前向動作與補償皆為純可呼叫物件(或經執行器以 JSON 動作清單),因此編排可在無任何真實副
作用下完整單元測試。補償為盡力而為:失敗的補償會被記錄,回溯繼續進行。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import Saga

    result = (Saga()
              .step("create", create_record, delete_record)
              .step("notify", send_email, None)          # 無需復原
              .step("move", move_file, restore_file)
              .run())

    if not result.ok:
        result.failed_step      # 哪個步驟拋出例外
        result.completed        # 前向執行過的步驟
        result.compensated      # 已復原的步驟(對已完成者 LIFO)

``run()`` 回傳 ``SagaResult``(``ok`` / ``completed`` / ``compensated`` /
``failed_step`` / ``error``)。步驟「失敗」即其動作拋出例外;沒有補償的步驟在回溯時直接略
過。

執行器指令
----------

``AC_run_saga`` 接受 ``steps`` —— 一個 ``{name, action: [...], compensation: [...]}``
的清單(或 JSON 字串),其中 ``action`` / ``compensation`` 各為一個 AutoControl 動作清單。
回傳 ``{ok, completed, compensated, failed_step, error}``。相同操作亦提供為 MCP 工具
``ac_run_saga``,以及 Script Builder 中 **Flow** 分類下的指令。
