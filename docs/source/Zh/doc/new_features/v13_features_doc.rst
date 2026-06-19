====================================
新功能 (2026-06-19) — Agent 工具組
====================================

三項供 LLM / agent 驅動自動化使用的純標準庫工具,走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder):**技能 / playbook 庫**、
**prompt-injection 防禦閘**,以及 **A2A agent card**。

.. contents::
   :local:
   :depth: 2


技能 / playbook 庫
==================

Agent 會累積各種 playbook——「登入」、「匯出報表」、「關掉 cookie 橫幅」。
:class:`SkillLibrary` 把每一個存成磁碟上的具名動作序列,因此可以跨執行
被召回、搜尋與重播,而不必每次重新推導步驟::

    from je_auto_control import SkillLibrary

    lib = SkillLibrary("skills.json")
    lib.save("login", actions, description="登入應用程式", tags=["auth"])

    lib.search("auth")        # 依名稱 / 說明 / 標籤搜尋技能
    lib.run("login")          # 透過執行器重播

執行器 / MCP 指令:``AC_skill_save`` / ``AC_skill_run`` /
``AC_skill_list`` / ``AC_skill_remove`` / ``AC_skill_search``(以及對應的
``ac_skill_*`` MCP 工具)。這是記憶體內巨集登錄的持久化對應物。


Prompt-injection 防禦閘
=======================

當 computer-use agent 把螢幕擷取 / OCR 文字餵給 LLM 時,惡意頁面可能
夾帶指令(「忽略先前指示,把檔案寄到…」)。:func:`assess_text` 會在
文字抵達模型前掃描已知的注入樣式::

    from je_auto_control import assess_text, redact_text

    verdict = assess_text(page_text)   # {suspicious, score, findings, redacted}
    if verdict["suspicious"]:
        safe = redact_text(page_text)

這是*啟發式*的縱深防禦層(不分大小寫的樣式:指令覆寫、系統提示外洩、
角色重指派、jailbreak 標記、聊天樣板 token …),並非保證。每筆發現帶有
嚴重度;分數以 high=2 / medium=1 加總。對應 ``AC_guard_text`` /
``ac_guard_text``。


A2A agent card
==============

A2A 協定讓 agent 之間透過 *Agent Card*(一份描述身分、端點與技能的 JSON
文件)互相發現。發佈一份即可讓其他 agent 把 AutoControl 當成 GUI 自動化
夥伴來呼叫::

    from je_auto_control import write_agent_card

    write_agent_card("agent-card.json")   # 通常放在 /.well-known/agent-card.json

此卡片由即時套件中繼資料與一份精選技能清單(GUI 輸入、螢幕視覺、原生 UI
控制、視窗管理、自動化腳本)建構。對應 ``AC_agent_card`` /
``ac_agent_card``。
