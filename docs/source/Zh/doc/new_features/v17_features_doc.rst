==========================================
新功能 (2026-06-19) — 反應式觀察器
==========================================

非阻塞的**螢幕觀察器**:在區域/條件上註冊監看,當被監看的目標**出現**、
**消失**或**改變**時,觸發回呼(或執行一段 action list)。這是阻塞式
``wait_for_*`` 的互補——流程可以在做其他事的同時對對話框、進度或狀態
變化做出反應(SikuliX 的 ``observe`` 模型)。

純標準庫;走完整五層(facade、``AC_*`` 執行器指令、MCP 工具、Script
Builder)。

.. contents::
   :local:
   :depth: 2


Python API
==========

::

    from je_auto_control import ScreenObserver, image_predicate, EVENT_APPEAR

    obs = ScreenObserver(poll_interval_s=0.5)
    obs.add("error-dialog",
            image_predicate("error.png", threshold=0.9),
            on_event=lambda event, value: dismiss(),
            events=(EVENT_APPEAR,))
    obs.start()                 # 背景輪詢執行緒
    ...
    obs.stop()

偵測與螢幕解耦:監看的 ``predicate`` 只回傳當前值(truthy 代表存在),
因此轉換邏輯可用合成值透過 ``poll_once()`` 做單元測試。內建的條件建構器
——:func:`image_predicate`、:func:`text_predicate`、
:func:`pixel_predicate`——包裝既有的 locate / OCR / pixel 輔助函式。

轉換:``appear``(不存在→存在)、``vanish``(存在→不存在)、``change``
(存在且值改變)。可用 ``events=`` 只訂閱其中一部分。


執行器 / MCP 指令
=================

* ``AC_observe_add`` — 監看 ``kind``(``image`` / ``text`` / ``pixel``)
  的 ``event``,觸發時執行 ``actions``(watchdog 模式,推廣到螢幕內容)。
* ``AC_observe_remove`` / ``AC_observe_list`` — 管理監看。
* ``AC_observe_poll`` — 評估每個監看一次並回傳觸發事件(決定性、免執行緒
  ——適合腳本/測試)。
* ``AC_observe_start`` / ``AC_observe_stop`` — 背景輪詢執行緒。

對應的 ``ac_observe_*`` MCP 工具提供相同介面。
