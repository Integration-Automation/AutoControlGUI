====================================
新功能 (2026-06-19) — 彈窗看門狗
====================================

無人值守自動化失敗的第一大主因,是腳本沒寫到的未預期對話框——UAC 提示、
「工作階段即將過期」橫幅、Windows Update 通知、電子報彈窗。彈窗看門狗以
並行的守衛執行緒監看註冊的 pattern,並在**獨立於主步驟序列**之外將其關閉,
讓長時間執行得以持續。

這由社群痛點研究指出為無人值守的頭號失敗主因。走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder),且完全 headless——matcher
與 action 皆可注入,因此不需真實桌面即可單元測試。

.. contents::
   :local:
   :depth: 2


快速開始
========

::

    from je_auto_control import default_popup_watchdog

    # 自動關閉任何標題含「Update Available」的視窗。
    default_popup_watchdog.add_window_rule("Update Available", action="close")
    # 對「Session expiring」對話框改按 Esc,而非關閉。
    default_popup_watchdog.add_window_rule("Session expiring", action="esc")
    default_popup_watchdog.start()
    ...                                  # 執行你的主流程
    default_popup_watchdog.stop()

``action`` 為 ``"close"``(關閉相符視窗)或要按的鍵名(``"enter"`` /
``"esc"`` / ...)。守衛在背景執行緒輪詢,並把每次關閉記錄在
``default_popup_watchdog.hits``。


自訂規則
========

對於非視窗的彈窗,註冊一條把*偵測器*與*關閉器*配對的通用規則::

    from je_auto_control import PopupWatchdog, WatchdogRule

    watchdog = PopupWatchdog(poll_interval_s=0.5)
    watchdog.add_rule(WatchdogRule(
        name="cookie-banner",
        matcher=lambda: locate_image_center("cookie.png") is not None,
        action=lambda: click_text("Accept"),
    ))

matcher/action 拋出例外的規則會被記錄並略過——單一壞規則絕不會讓守衛迴圈
停擺。


執行器指令
==========

* ``AC_watchdog_add`` — 註冊視窗規則(``title`` + ``action``)。
* ``AC_watchdog_start`` / ``AC_watchdog_stop`` — 控制守衛執行緒。
* ``AC_watchdog_list`` — 回報執行狀態、規則與關閉紀錄。

典型的無人值守腳本會在主工作之前先加規則並啟動看門狗,讓任何雜散對話框
被自動清除。
