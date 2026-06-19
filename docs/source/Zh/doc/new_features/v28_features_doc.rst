==================================================
新功能 (2026-06-19) — 流程文件(SOP)產生器
==================================================

把錄製 / 編寫的動作清單轉成編號、人類可讀的**標準作業程序(SOP)**——
結構化步驟清單加上 HTML 呈現(UiPath Task-Capture 的產出),供 runbook
與審閱使用。純標準庫;走完整五層。

.. contents::
   :local:
   :depth: 2


用法
====

::

    from je_auto_control import generate_sop, write_sop

    doc = generate_sop(actions, title="Invoice Login")
    doc["steps"]        # [{n, command, description, args}, ...]
    doc["html"]         # 完整 HTML 文件(內容已轉義)
    write_sop(actions, "procedure.html", title="Invoice Login")

每個動作會對應到人類動詞片語(``AC_write`` → 「Type text」、
``AC_click_mouse`` → 「Click the mouse」…),並附上最具描述性的引數;
未知指令則退回為可讀的名稱形式。使用者內容會做 HTML 轉義。對應
``AC_generate_sop`` / ``ac_generate_sop``(給 ``path`` 時寫檔,否則回傳
結構化文件)。
