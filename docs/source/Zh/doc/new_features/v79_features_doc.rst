Dotenv(.env)解析
================

``script_vars.load_vars_from_json`` 可載入扁平 JSON,但沒有任何東西讀取 de-facto 12-factor 的
``.env`` 檔案。本功能把 ``KEY=VALUE`` 行 —— 遵循 ``export`` 前綴、單/雙引號、轉義與行內註解 ——
解析成可餵給設定層的純 dict,且不依賴 ``python-dotenv``。

純標準函式庫(``re``);不匯入 ``PySide6``。``parse_dotenv`` 為純字串轉 dict 函式,載入器會合併進
呼叫端提供的 mapping 而非變動 ``os.environ``,因此安全且具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import parse_dotenv, load_dotenv, dotenv_values, dump_dotenv

    values = parse_dotenv('PLAIN=hello\nexport TOKEN="a\\nb"  # comment')
    # {"PLAIN": "hello", "TOKEN": "a\nb"}

    config = {}
    load_dotenv(".env", config)                 # 把檔案合併進 dict
    load_dotenv(".env.local", config, override=True)

``parse_dotenv`` 略過空白與 ``#`` 註解行,去除選用的 ``export`` 前綴,驗證鍵,並解析值:單引號值為
字面值,雙引號值處理 ``\n`` / ``\t`` / ``\\`` / ``\"`` 轉義,未加引號的值會去除結尾 `` #`` 註解與
前後空白。``dotenv_values`` 讀取並解析檔案;``load_dotenv`` 把檔案合併進明確的 ``env`` mapping
(預設保留既有鍵,除非 ``override``);``dump_dotenv`` 把 mapping 序列化回 ``.env`` 文字,並為需要的值
加上引號。

執行器命令
----------

``AC_parse_dotenv`` 把 ``text`` 解析成 ``{values}``;``AC_load_dotenv`` 從 ``path`` 讀檔載入到新的
``{values}`` dict。兩者皆以 MCP 工具(``ac_parse_dotenv`` / ``ac_load_dotenv``)以及 Script Builder
中 **Data** 分類下的命令提供。
