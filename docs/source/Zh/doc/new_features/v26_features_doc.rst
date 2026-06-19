==================================================
新功能 (2026-06-19) — CI 註解與剪貼簿歷史
==================================================

兩項純標準庫工具:從結果輸出 CI 註解,以及保存可搜尋的剪貼簿歷史。
走完整五層。

.. contents::
   :local:
   :depth: 2


CI 工作流程註解
===============

::

    from je_auto_control import emit_annotations

    emit_annotations([
        {"level": "error", "message": "step failed",
         "file": "flows/login.json", "line": 12, "title": "Login"},
    ])
    # 印出:::error file=flows/login.json,line=12,title=Login::step failed

把結果 dict(``{level, message, file?, line?, col?, title?}``)轉成 GitHub
Actions 工作流程命令,讓失敗在 PR 中**行內**顯示——不需第三方 reporter
action。``level`` 為 ``error`` / ``warning`` / ``notice``;值會依 GitHub
規則轉義。對應 ``AC_ci_annotations`` / ``ac_ci_annotations``。


剪貼簿歷史
==========

::

    from je_auto_control import ClipboardHistory, default_clipboard_history

    default_clipboard_history.start()      # 背景輪詢剪貼簿
    default_clipboard_history.search("invoice")
    default_clipboard_history.get(0)        # 最近一筆

一個有上限、最新在前、去重的剪貼簿文字環狀緩衝,具 ``add`` / ``snapshot``
/ ``get`` / ``search`` / ``clear`` 及可選的背景輪詢器(``start`` / ``stop``
/ ``capture_once``)。對應 ``AC_clip_history_capture`` /
``AC_clip_history_list`` / ``AC_clip_history_search`` /
``AC_clip_history_start`` / ``AC_clip_history_stop``(以及 ``ac_clip_history_*``)。
