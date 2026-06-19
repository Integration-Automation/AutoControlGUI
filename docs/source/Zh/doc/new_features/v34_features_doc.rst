網路出口允許清單守衛
====================

能連到任意主機的無人值守自動化是一種資料外洩風險。``EgressPolicy`` 讓操作者釘選無頭
HTTP 用戶端可連線的主機。它會被每一次
:func:`~je_auto_control.utils.http_client.http_client.http_request` 呼叫(因而也包含
``AC_http`` 與所有以其為基礎的功能)所諮詢,因此鎖定出口即可一次涵蓋整個框架。

此策略支援**允許(allow)**清單(預設拒絕 —— 僅符合的主機可通過)與/或**拒絕
(deny)**清單(即使其他情況允許也封鎖)。樣式為對 URL 主機名稱進行不分大小寫的
:mod:`fnmatch` 萬用比對,例如 ``*.example.com`` 或 ``localhost``。模組層級的策略以
*allow-all* 模式啟動,因此在操作者鎖定前**不會改變任何行為**。純標準函式庫,不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import set_egress_policy, EgressBlocked, http_request

    set_egress_policy(allow=["*.internal.corp", "api.example.com"])

    http_request("https://api.example.com/v1")     # 通過
    try:
        http_request("https://evil.test/")          # 連線前即拋出
    except EgressBlocked:
        ...

    set_egress_policy(None, None)                    # 回到 allow-all

模式:``allow=None`` 為 allow-all;``allow=[]`` 拒絕一切;單獨給 ``deny=[...]`` 僅封鎖
那些主機。``allow`` / ``deny`` 皆可接受清單或單一逗號分隔字串。
``get_egress_policy().is_allowed(url)`` 可在不拋出例外的情況下檢查 URL;
``EgressPolicy(allow=..., deny=...)`` 則建立獨立的策略物件。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_egress_allow``              將 HTTP 用戶端鎖定到 ``allow`` / ``deny`` 清單。
``AC_egress_check``              回報 URL 的 ``{allowed}``(不拋出例外)。
``AC_egress_reset``              將策略清回 allow-all。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_egress_allow`` / ``ac_egress_check`` /
``ac_egress_reset``),以及 Script Builder 中 **Tools** 分類下的指令。
