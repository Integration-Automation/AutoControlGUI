URI-Scheme 值參照
================

``script_vars.interpolate`` 把單一間接寫死(``${secrets.NAME}`` → vault),而 ``AssetStore`` 的憑證
參照僅限 vault 名稱。沒有一個通用、可插拔的讀取時間接機制 —— 也就是現代設定模式:儲存一個*指標*
(``env://TOKEN``、``file://./token``、``secret://api-key``)而非值本身。本功能補上這個解析器。

純標準函式庫(``os`` / ``re``);不匯入 ``PySide6``。env 讀取器、secret 解析器與基底目錄皆可注入,因此
解析安全且在 CI 中具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import resolve_ref, resolve_refs_in, RefResolver

    token = resolve_ref("env://API_TOKEN")
    key = resolve_ref("file://./secrets/key.pem")

    config = resolve_refs_in({
        "token": "env://API_TOKEN",
        "db": {"password": "secret://db-password"},
    })

``resolve_ref`` 解析單一參照:``env://`` 讀取環境變數(來自可注入的 mapping,否則回退 ``os.environ``),
``file://`` 讀取檔案(可選的 ``base_dir`` realpath 防穿越保護),``secret://`` 委派給可注入的解析器或
governance 憑證 broker。``resolve_refs_in`` 走訪巢狀 dict/list 並就地解析每個參照,非參照值保持不變。
``is_ref`` 測試一個值,``RefResolver`` 把可注入後端打包以便重複使用。無法解析或未知 scheme 的參照會拋出
``SecretRefError``。

執行器命令
----------

``AC_resolve_ref`` 把單一 ``ref`` 解析成 ``{value}``;``AC_resolve_refs`` 解析 ``obj`` 內每個參照並回傳
``{resolved}``。兩者皆以 MCP 工具(``ac_resolve_ref`` / ``ac_resolve_refs``)以及 Script Builder 中
**Security** 分類下的命令提供。
