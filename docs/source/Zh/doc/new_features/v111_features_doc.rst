雙向文字 QA(Trojan-Source 掃描)
================================

``confusables`` 抓出相似的*字元*,但隱形的 Unicode *方向格式控制*是另一種危害。嵌入/覆寫
(LRE/RLE/LRO/RLO/PDF)、隔離(LRI/RLI/FSI/PDI)與標記(LRM/RLM/ALM)可以悄悄改變文字的呈現順序。這既是
RTL 在地化 QA 的缺口,也是「Trojan Source」攻擊(CVE-2021-42574)的根源——覆寫控制讓原始碼讀起來與實際執行
不同。

本功能回報字串中的雙向控制字元、檢查嵌入/隔離是否平衡、推斷基底方向,並標記 Trojan-source 式的格式。
純標準函式庫(``unicodedata``);不匯入 ``PySide6``。每個函式皆為純函式,因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        detect_bidi_issues, bidi_controls, has_bidi_controls,
        is_bidi_balanced, base_direction, is_trojan_source,
        strip_bidi_controls,
    )

    sneaky = "value = <RLO>admin<PDF>"     # RLO ... PDF
    detect_bidi_issues(sneaky)
    # {'controls': [{'index': 8, 'char': '<RLO>', 'name': 'RLO'}, ...],
    #  'has_controls': True, 'balanced': True, 'base_direction': 'LTR',
    #  'trojan_source': True}

    is_trojan_source(sneaky)        # True
    strip_bidi_controls(sneaky)     # 'value = admin'
    base_direction("אב")            # 'RTL'

``bidi_controls`` 將每個控制字元列為 ``{index, char, name}``。``is_bidi_balanced`` 檢查 PDF 關閉一個嵌入/覆寫、
PDI 關閉一個隔離,且正確巢狀。``base_direction`` 依第一個強方向字元回傳 ``LTR`` / ``RTL`` / ``NEUTRAL``。
``is_trojan_source`` 在出現任何非標記格式控制或巢狀不平衡時為真。``strip_bidi_controls`` 回傳乾淨副本。
``detect_bidi_issues`` 將全部打包為一份報告。

執行器命令
----------

``AC_bidi_check`` 回傳完整報告;``AC_bidi_strip`` 回傳移除控制字元後的 ``{text}``。兩者皆以 MCP 工具
(``ac_bidi_check`` / ``ac_bidi_strip``)以及 Script Builder 中 **Data** 分類下的命令提供。
