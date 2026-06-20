行事曆週期規則(RRULE)
=====================

排程器的 cron 只是間隔式的 5 欄位 —— 無法表達「每月第 2 個星期二」、「每月最後一個工作日」或
「連續 10 次的每個工作日」。本功能補上 RFC 5545(iCalendar)**RRULE** 解析器與發生時刻展開器,
即 cron 之上的行事曆層。

支援的規則部分:``FREQ``(DAILY/WEEKLY/MONTHLY/YEARLY)、``INTERVAL``、``COUNT``、``UNTIL``、
``BYDAY``(含序數如 ``2MO`` / ``-1FR``)、``BYMONTHDAY``(含負數)、``BYMONTH``、``BYSETPOS``
與 ``WKST``。時間層級部分以及 BYWEEKNO/BYYEARDAY 不在範圍內。純標準函式庫(``datetime`` +
``calendar``);時鐘可注入,因此 ``next_occurrence`` 具決定性。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    import datetime
    from je_auto_control import parse_rrule, occurrences, next_occurrence

    rule = parse_rrule("FREQ=MONTHLY;BYDAY=2TU")     # 每月第 2 個星期二
    start = datetime.datetime(2026, 1, 1, 9, 0)

    for moment in occurrences(rule, start, count=3):
        print(moment)            # 2026-01-13 09:00、2026-02-10 09:00、...

    # 「每月最後一個工作日」
    last = parse_rrule("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1")

    # 在指定時間當下或之後的下一次(注入 now 以取得決定性)
    nxt = next_occurrence(rule, start, now=datetime.datetime(2026, 3, 15))

``parse_rrule`` 接受帶或不帶 ``RRULE:`` 前綴的規則,回傳凍結的 ``Recurrence``。``occurrences``
產生以 ``dtstart`` 為錨點的 datetime(其時刻與時區會套用到每一次發生),受 ``COUNT`` / ``UNTIL``
(或 ``count=`` / ``until=`` 覆寫)及安全上限約束。僅含日期的 ``UNTIL`` 會包含整天。
``next_occurrence`` 回傳在 ``now`` 當下或之後的第一次發生。

執行器命令
----------

``AC_rrule_occurrences`` 接受 ``rule`` 與 ISO ``dtstart``(及選用的 ``count``),回傳
``{occurrences}`` 為 ISO datetime。``AC_rrule_next`` 接受 ``rule`` / ``dtstart`` / 選用的
``now``,回傳 ``{next}``。兩者皆以 MCP 工具(``ac_rrule_occurrences`` / ``ac_rrule_next``)以及
Script Builder 中 **Flow** 分類下的命令提供。
