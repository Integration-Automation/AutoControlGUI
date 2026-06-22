等待視窗標題(正則)
==================

``wait_for_window`` 以*子字串*比對視窗標題且僅等待其*出現*;``wait_until_window_closed`` 為子字串消失。兩者都
不支援正則表達式標題或「等到使用中視窗標題符合 P」——例如等待瀏覽器分頁導覽至 ``r".*— Checkout$"``。本功能
為 ``smart_waits`` 家族加入正則標題等待。

標題來源可注入,因此迴圈可在無真實視窗下做無頭測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import wait_until_window_title

    wait_until_window_title(r".*— Checkout$", timeout_s=20)   # 分頁已導覽
    wait_until_window_title("Updating", present=False)         # 對話框消失
    wait_until_window_title("Checkout", regex=False)           # 子字串模式

預設 ``pattern`` 為正則表達式(``re.search``);傳入 ``regex=False`` 改用純子字串比對。``present=False`` 等待
標題*消失*。結果為 ``WaitOutcome``(``succeeded`` / ``reason`` / ``elapsed_s`` / ``samples_taken``);
``title_lister`` 可注入以供測試。

執行器命令
----------

``AC_wait_window_title`` 接受 ``pattern`` 以及 ``present`` / ``regex`` / ``timeout_s`` / ``poll_interval_s``,
並回傳 ``WaitOutcome`` dict。它以 MCP 工具 ``ac_wait_window_title`` 以及 Script Builder 中 **Flow** 分類下的命令
提供。
