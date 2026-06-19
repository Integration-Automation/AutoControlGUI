即時(Just-In-Time)憑證租約
============================

交給自動化的長效密鑰是一種長期負債。``CredentialBroker`` 實踐**零常駐權限(zero
standing privilege)**:使用者取得短效的*租約(lease)*—— 一個綁定密鑰名稱並帶有
到期時間的 token —— 真正的值僅在 :meth:`redeem` 時、且僅在租約有效期間,透過可插拔
的*解析器(resolver)*取得(已解鎖的 ``SecretManager`` 的 ``get``、環境變數查詢、
vault 用戶端)。已過期或已撤銷的租約取不到任何值。

密鑰值永遠不會進入 executor/MCP 紀錄:executor 與 MCP 介面僅管理租約*生命週期*。
回傳真正值的 :meth:`redeem` 是刻意設計的**僅限 Python API**逃生門,供必須處理密鑰
的程式使用。本模組為純標準函式庫,不匯入 ``PySide6``;時鐘與解析器皆可注入,因此到
期行為可被確定性地測試。

無頭 API
--------

.. code-block:: python

    from je_auto_control import CredentialBroker

    broker = CredentialBroker(resolver=secret_manager.get)   # resolver(name)->value
    token = broker.lease("db_password", ttl=120)             # 取得 token,而非值

    if broker.is_valid(token):
        password = broker.redeem(token)     # 即時取得,僅限 Python
        connect(password)

    broker.revoke(token)                     # 或讓它在 ttl 秒後自然過期

``active()`` 以 ``{token, name, ttl_remaining}`` 列出未過期的租約,不含任何值。模組
層級的 :data:`default_broker` 支撐 executor/MCP 指令;以 ``set_secret_resolver(fn)``
設定一次其解析器即可。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_lease_secret``              為 ``name`` 發出租約(``ttl`` 秒);``{token, ttl}``。
``AC_lease_valid``               回報租約 token 的 ``{valid}``。
``AC_revoke_lease``              撤銷租約 token;``{revoked}``。
``AC_lease_active``              列出有效租約(不含密鑰值)。
================================ ===================================================

executor、MCP 與 Script Builder 介面刻意**沒有** redeem 指令 —— 在那些介面暴露值會
使其洩漏進執行紀錄。Redeem 僅限 Python。相同的生命週期操作亦提供為 MCP 工具
(``ac_lease_secret`` / ``ac_lease_valid`` / ``ac_revoke_lease`` /
``ac_lease_active``),以及 Script Builder 中 **Tools** 分類下的指令。
