確保控制項處於目標狀態(冪等)
==============================

*無條件採取行動*的自動化——「點選核取方塊」、「輸入該值」——會把已勾選的方塊再次切換,或對已正確的
欄位重新輸入,且無法安全地重跑。穩健的型態是讀取-比較-行動-驗證:看目前狀態,若已相符就什麼都不做,
否則套用變更並確認生效。``ensure_state`` 正是此原語。

* :func:`ensure_state` ——通用:透過 ``reader`` 讀取,若不等於 ``desired`` 就套用 ``setter`` 並
  重讀,最多 ``attempts`` 次。
* :func:`ensure_toggle` ——針對無狀態翻轉的布林特化:讀取 ``is_on``,僅在與 ``desired`` 不同時
  呼叫 ``toggle``。

已處於目標狀態的控制項會保持不動(``changed=False``),故此呼叫是冪等且可安全重跑。這有別於
:mod:`idempotency`(請求鍵重放快取)——``ensure_state`` 收斂的是*裝置狀態*,而非呼叫結果。
reader / setter / toggle 接縫皆可注入,故邏輯能在沒有真實控制項的情況下完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import ensure_state, ensure_toggle

    # 冪等地把某設定設為 "on" ——若已是則不寫入
    ensure_state("on", reader=read_combo, setter=write_combo)
    # -> {'ok': True, 'changed': False, 'value': 'on', 'attempts': 0}

    # 僅在尚未勾選時把核取方塊翻為勾選
    ensure_toggle(True, is_on=is_checked, toggle=click_checkbox)

兩者皆回傳 ``{ok, changed, value, attempts}``:``changed`` 告訴你是否實際執行了動作
(對「我是否得修正它?」的報告很有用),``ok`` 則是是否在 ``attempts`` 內達到目標狀態。
對 :func:`ensure_state` 傳入自訂 ``equals`` 可做不分大小寫或正規化比較。

執行器指令
----------

``AC_ensure_field_value``(``desired`` 加上 ``name`` / ``role`` / ``app_name`` /
``automation_id`` / ``attempts`` → ``{ok, changed, value, attempts}``)透過無障礙後端
冪等地設定原生控制項的值——先讀取,若已相符則不做任何事。以對應的 ``ac_ensure_field_value``
MCP 工具及 Script Builder 指令(位於 **Flow** 分類下)形式提供。:func:`ensure_state` /
:func:`ensure_toggle`(接受任意 callable)則是 Python API 介面。
