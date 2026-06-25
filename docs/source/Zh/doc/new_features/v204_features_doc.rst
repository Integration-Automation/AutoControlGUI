閒置偵測 + 保持機器清醒
=======================

長時間無人值守的自動化執行常因兩種情況中斷:螢幕保護 / 電源原則在執行中途讓機器睡眠,或是當有人正在
使用機器時執行應該暫停。框架原本兩種訊號都沒有。``idle_keepawake`` 補上這兩者,並以可注入接縫實作,
所有邏輯都能在不碰作業系統的情況下測試。

* :func:`idle_seconds` / :func:`is_idle` ——距離使用者上次鍵盤 / 滑鼠輸入的秒數(Windows 上用
  ``GetLastInputInfo``),透過可注入的 ``probe`` 取得。
* :func:`plan_keep_awake` ——純 planner,描述請求對應到哪些清醒旗標。
* :func:`keep_awake` ——具範圍的 context manager,在 ``with`` 區塊期間保持機器清醒,離開時還原先前狀態。
* :func:`keep_awake_on` / :func:`allow_sleep` ——供 JSON 動作流程使用的行程全域開 / 關配對。

三個 keep-awake 入口皆透過可注入的 ``driver`` 套用計畫(預設 Windows 用
``SetThreadExecutionState``、macOS 用 ``caffeinate``、Linux 用 ``systemd-inhibit``)。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        idle_seconds, is_idle, keep_awake, keep_awake_on, allow_sleep,
    )

    idle_seconds()          # 例如 3.4 ——距離上次輸入的秒數
    is_idle(300)            # 沒人碰機器滿 5 分鐘後回傳 True

    # 具範圍:只在長步驟執行時保持清醒
    with keep_awake():
        run_long_batch()

    # 流程式:開始時開、結束時關
    keep_awake_on(display=True, system=True)
    try:
        run_long_batch()
    finally:
        allow_sleep()

:func:`is_idle` 是「只在使用者離開時才執行」的判斷閘;:func:`keep_awake` /
:func:`keep_awake_on` 阻止螢幕與系統睡眠,讓整夜執行不被打斷。``display=False`` 會保持系統清醒但允許
螢幕變黑(對無頭機器較省電)。

執行器指令
----------

``AC_idle_seconds``(→ ``{idle_seconds}``)、``AC_is_idle``(``threshold`` →
``{idle, idle_seconds}``)、``AC_plan_keep_awake``(``display`` / ``system`` → 計畫)、
``AC_keep_awake_on``(``display`` / ``system`` → 生效中的計畫)與 ``AC_allow_sleep``
(→ ``{released}``)。皆以對應的 ``ac_*`` MCP 工具(讀取為唯讀、keep-awake 開 / 關為僅副作用)
及 Script Builder 指令(位於 **Shell** 分類下)形式提供。:func:`keep_awake` context manager
則是具範圍使用的 Python API 介面。
