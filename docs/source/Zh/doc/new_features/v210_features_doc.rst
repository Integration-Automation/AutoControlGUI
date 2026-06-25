輸入後驗證欄位
==============

``field_entry`` 對控制項輸入後就*指望*它生效了。緩慢的 IME、焦點被搶、輸入遮罩或自動格式化都可能
悄悄竄改或漏掉字元,而沒有任何東西讀回欄位來察覺。這有別於 ``action_effect``(目標附近是否有*任何*
變化?)與 ``postcondition.text_present``(該文字是否出現在畫面*某處*?)——兩者都無法確認*這個*欄位
現在等於*這個*值。``verify_field`` 補上讀回這道缺口。

* :func:`compare_field_value` ——純函式:在某個比對 ``mode`` 下比較預期與實際值——
  ``exact`` / ``trim`` / ``ci``(不分大小寫)/ ``normalized``(Unicode NFKC + 大小寫摺疊 + 空白)/
  ``contains``。
* :func:`verify_field_value` ——透過可注入的 ``reader`` 讀回欄位並比較。
* :func:`fill_and_verify` ——透過可注入的 ``filler`` 輸入、讀回、並重試(可選擇先清空),
  直到相符或用完次數。

在執行器中,reader 即原生無障礙值,但每個比較與重試決策都是純函式,可在沒有真實控制項的情況下測試。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        compare_field_value, verify_field_value, fill_and_verify,
    )

    compare_field_value("café", "café", mode="normalized")["match"]  # True

    # 讀回控制項並斷言它取得了該值
    ok = verify_field_value("invoice.pdf",
                            reader=lambda: read_control_value())["match"]

    # 輸入、讀回、最多重試 3 次(每次重試前先清空)
    fill_and_verify("2026-06-26", filler=type_into_field,
                    reader=read_control_value, attempts=3, clear=select_all_del)

``fill_and_verify`` 回傳最終的 :func:`compare_field_value` 結果加上 ``attempts`` 次數,
讓流程能在持續不符時分支處理,而非盲目輸入。``filler`` / ``reader`` / ``clear`` 皆可注入,
故重試邏輯能在沒有真實欄位的情況下完整測試。

執行器指令
----------

``AC_compare_field_value``(``expected`` / ``actual`` / ``mode`` → ``{match,
mode, expected, actual}``,純函式)與 ``AC_verify_field_value``(``expected`` 加上
``name`` / ``role`` / ``app_name`` / ``automation_id`` / ``mode`` → 比對結果,
透過無障礙後端讀取控制項的值)。皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令
(位於 **Flow** 分類下)形式提供。:func:`fill_and_verify`(包裹一個輸入 callable)則是 Python API 介面。
