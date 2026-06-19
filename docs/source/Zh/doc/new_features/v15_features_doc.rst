========================================
新功能 (2026-06-19) — 記憶與決定性
========================================

由 agent / QA 研究輪找出的兩項純標準庫工具,走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder):持久化的 **agent
情節記憶**,以及**決定性執行**工具。

.. contents::
   :local:
   :depth: 2


Agent 情節記憶
==============

每次執行都重新推導「這個 app 怎麼登入」很浪費 token,也會重複犯錯。
:class:`AgentMemory` 把每段情節——目標、軌跡(步驟 / 工具呼叫)、結果
——寫入 SQLite 檔,並依關鍵字召回最相關的過往情節,注入規劃器的脈絡::

    from je_auto_control import AgentMemory

    mem = AgentMemory("agent.memory.db")
    mem.remember("登入帳務入口", steps=recorded_actions,
                 outcome="success", tags=["auth"])

    for episode in mem.recall("入口 登入", limit=3):
        ...   # 把 episode.goal / episode.steps 回饋給規劃器

召回時以目標 + 標籤 + 結果上的詞頻為每段情節評分(免相依的 BM25 替代);
日後可在不改 API 的情況下加上向量層。指令:``AC_memory_remember`` /
``AC_memory_recall`` / ``AC_memory_recent`` / ``AC_memory_forget`` /
``AC_memory_stats``(以及對應的 ``ac_memory_*`` MCP 工具)。


決定性執行
==========

時間與隨機是自動化不穩定(flaky)的兩大主因。:class:`DeterministicRun`
在 ``with`` 區塊內把兩者都固定下來,並記錄選擇以便完全重現::

    from je_auto_control import DeterministicRun

    with DeterministicRun(seed=42, freeze_time=1_750_000_000.0) as run:
        ...                      # random.* 可重現;time.time() 被凍結
    manifest = run.manifest()    # {"seed": 42, "freeze_time": 1750000000.0}

範圍(純標準庫——不需 ``freezegun``):為全域 :mod:`random` 產生器(若有
numpy 也一併)設種子並於離開時還原狀態,並把 ``time.time`` /
``time.time_ns`` 修補為固定時刻。``time.monotonic`` 刻意保持不變,讓
時間長度量測與逾時仍正常運作。

``seed_everything(seed)`` 是獨立的設種子輔助函式,亦以 ``AC_seed_everything``
/ ``ac_seed_everything`` 形式提供,供流程做全執行重現。
