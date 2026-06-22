JSON Schema 驗證
================

框架過去只會*產生* JSON Schema(action-lint、tool-use schema),而
``data_quality.validate_rows`` 是扁平、逐欄的表格檢查器 —— 兩者都無法以真正的 schema 驗證
巢狀的 API 請求/回應內容。這補上了缺少的消費端:以 JSON Schema(Draft 2020-12 子集)驗證
一個記憶體中的值,並以可讀的路徑回報**每一個**違規。

``validate_json`` 回傳 ``SchemaValidationResult``(``ok`` 加上一個由
``{path, keyword, message}`` 組成的 ``errors`` 清單);``is_valid`` 是布林捷徑;
``assert_schema`` 會以彙整後的摘要拋出 ``AutoControlAssertionException``。純標準函式庫
(``re``);不匯入 ``PySide6``。

支援的關鍵字
------------

* ``type`` —— 包含 ``integer`` 會匹配整數值的浮點數(``5.0``)但永不匹配布林值;
  ``enum`` / ``const``(讓 ``True`` 與 ``1`` 保持相異)。
* 數字 —— ``minimum`` / ``maximum`` / ``exclusiveMinimum`` / ``exclusiveMaximum`` /
  ``multipleOf``。
* 字串 —— ``minLength`` / ``maxLength`` / ``pattern``。
* 陣列 —— ``minItems`` / ``maxItems`` / ``uniqueItems`` / ``items`` /
  ``prefixItems`` / ``contains``。
* 物件 —— ``required`` / ``minProperties`` / ``maxProperties`` / ``properties`` /
  ``patternProperties`` / ``additionalProperties``。
* 組合器 —— ``allOf`` / ``anyOf`` / ``oneOf`` / ``not``;布林 schema(``True`` /
  ``False``);本地 ``$ref``(``#/$defs/...`` JSON Pointer)。

遠端 ``$ref`` 與 ``format`` 斷言刻意排除在範圍之外。

無頭 API
--------

.. code-block:: python

    from je_auto_control import validate_json, is_valid, assert_schema

    schema = {
        "type": "object",
        "required": ["name", "age"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "age": {"type": "integer", "minimum": 0, "maximum": 130},
            "roles": {"type": "array", "items": {"enum": ["admin", "user"]},
                      "uniqueItems": True},
        },
    }

    result = validate_json({"name": "", "age": 200, "extra": 1}, schema)
    # result.ok 為 False
    for error in result.errors:
        print(error["path"], error["keyword"], "-", error["message"])
    # $.name minLength - shorter than 1
    # $.age  maximum   - greater than maximum 130
    # $.extra additionalProperties - additional property not allowed

    if is_valid(payload, schema):
        ...                         # 布林捷徑

    assert_schema(payload, schema)  # 遇到第一個無效值即拋出

這與既有的 ``json_query``(擷取一個值)以及 ``http_request`` 輔助函式(在處理前先驗證 API
回應內容)自然搭配。

執行器命令
----------

``AC_validate_json`` 接受 ``data`` 與 ``schema``(各為 list/object 或 JSON 字串),回傳
``{ok, errors}``。同一操作亦以 MCP 工具 ``ac_validate_json`` 以及 Script Builder 中
**Data** 分類下的命令提供。
