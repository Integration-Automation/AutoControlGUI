易混淆字元 / 同形異義字偵測
==========================

``secrets_scan`` 找出疑似機密的權杖、``guardrail`` 篩檢提示注入,但沒有任何功能能抓出*視覺*仿冒:西里爾字母
``"а"``(U+0430)與拉丁字母 ``"a"``(U+0061)在像素上完全相同,因此 ``"pаypal"``(其中 ``а`` 為西里爾字母)
對人類讀來就是 ``"paypal"``,但比較卻不相等——這正是 IDN 同形異義字釣魚與仿冒 UI 標籤的根源。

本功能參照 Unicode TR39 的概念,將易混淆字元折疊為原型*骨架*(skeleton)(兩字串骨架相同即為易混淆),並標記
混用多種文字系統的字串。純標準函式庫(``unicodedata``);不匯入 ``PySide6``。每個函式皆為純函式,因此在 CI 中
完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        confusable_skeleton, is_confusable, detect_homoglyphs,
        is_mixed_script, scripts_of,
    )

    confusable_skeleton("pаypal")          # 'paypal'  (西里爾 а -> a)
    is_confusable("pаypal", "paypal")      # True
    detect_homoglyphs("pаypal")            # [{'index': 1, 'char': 'а', 'prototype': 'a'}]
    is_mixed_script("pаypal")              # True  (拉丁 + 西里爾)
    scripts_of("pаypal")                   # {'LATIN', 'CYRILLIC'}

``confusable_skeleton`` 先以 NFKC 正規化(折疊全形、連字與數學英數字),再將每個剩餘的跨文字系統仿冒字對映到
其拉丁原型。``is_confusable`` 僅在兩個*不同*字串骨架相同時為真。``detect_homoglyphs`` 回傳有問題的字元連同其
位置與原型。``scripts_of`` / ``is_mixed_script`` 依 Unicode 區塊將字元分類(忽略數字、標點與空白),因此可單獨
標記一個混用文字系統的權杖。

執行器命令
----------

``AC_confusable_scan`` 對單一字串回傳 ``{skeleton, homoglyphs, mixed_script, scripts}``;``AC_confusable_compare``
對一組字串回傳 ``{confusable}``。兩者皆以 MCP 工具(``ac_confusable_scan`` / ``ac_confusable_compare``)以及
Script Builder 中 **Data** 分類下的命令提供。
