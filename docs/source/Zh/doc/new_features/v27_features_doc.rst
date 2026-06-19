==================================================
新功能 (2026-06-19) — 修復分析與機密掃描
==================================================

兩項純標準庫的稽核/分析工具:把自我修復記錄彙總成漂移指標,以及掃描
action JSON 中的寫死機密。走完整五層。

.. contents::
   :local:
   :depth: 2


自我修復分析
============

::

    from je_auto_control import analyze_heal_log, heal_stats

    analyze_heal_log(limit=200)     # 針對即時自我修復記錄
    heal_stats(events)               # 針對提供的事件清單

把自我修復事件彙總成 ``{total, healed, heal_rate, by_method, fallbacks,
fallback_rate, avg_duration_ms, top_brittle}``——在定位器真正失效前,揪出
越來越需要 VLM 後備(衰退中的選擇器)的那些。對應 ``AC_heal_stats`` /
``ac_heal_stats``。


機密掃描
========

::

    from je_auto_control import scan_secrets

    scan_secrets(action_json)   # [{path, kind, preview}, ...]

走訪 JSON 結構並標記看起來像機密的字串值——依鍵名(``password`` /
``token`` / ``api_key`` …)、依值樣式(AWS / GitHub token、私鑰區塊),或
依高夏農熵——這些應改用保險庫(``${secrets.NAME}``)。已引用保險庫的值會被
略過;預覽會遮罩。對應 ``AC_scan_secrets`` / ``ac_scan_secrets``。
