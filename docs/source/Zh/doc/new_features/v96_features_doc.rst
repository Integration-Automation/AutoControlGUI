JSON-Schema 相容性檢查
=====================

我們能*依*某個 JSON Schema 驗證(``json_schema``)並*產生*結構(``action_lint/schema``),但無法回答
「使用舊結構的消費者,是否仍能讀取以新結構寫入的資料?」—— 也就是依 Confluent/Avro 的 backward /
forward / full 規則分類變更(新增必填欄位、移除欄位、收窄型別、移除 enum 值)。本功能補上此分類器。

範圍:``json_schema`` 理解的物件結構子集 —— ``properties`` / ``required`` / ``type`` / ``enum``。純標準
函式庫;不匯入 ``PySide6``。每個函式皆為純函式(兩個結構 dict 輸入、報告輸出),因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        check_compatibility, is_backward_compatible, diff_schemas,
    )

    report = check_compatibility(old_schema, new_schema, mode="backward")
    # {"compatible": False, "mode": "backward",
    #  "changes": [...], "breaking": [{"path": "email", "kind": "field_added",
    #                                  "breaks": ["backward"]}]}

    if not is_backward_compatible(old_schema, new_schema):
        block_release()

``diff_schemas`` 把每個變更分類為 ``SchemaChange``(``path``、``kind``、``breaks``)。會破壞 backward 的
變更包含新增必填欄位、收窄型別、移除 enum 值;會破壞 forward 的變更包含移除必填欄位、放寬型別、新增
enum 值。``check_compatibility`` 依 ``mode``(``backward`` / ``forward`` / ``full``)篩選;
``is_backward_compatible`` / ``is_forward_compatible`` / ``is_full_compatible`` 為布林捷徑。

執行器命令
----------

``AC_check_compatibility`` 接受 ``old`` / ``new`` 結構與選用的 ``mode``,回傳
``{compatible, mode, changes, breaking}``。它以 MCP 工具 ``ac_check_compatibility`` 以及 Script Builder
中 **Data** 分類下的命令提供。
