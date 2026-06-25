鎖定工作站 + 等待解鎖
====================

:mod:`session_guard` 回答「目前 session 是否鎖定?」並在鎖定時丟出例外。缺少的另一半是對鎖定狀態
*採取行動*:在無人值守執行結束時鎖定機器、在恢復前阻塞直到有人解鎖,或把一連串鎖定狀態取樣化約為
鎖定 / 解鎖事件。``lock_session`` 補上這些,並以可注入接縫實作,故邏輯能在不碰作業系統的情況下測試。

* :func:`lock_session` ——立即鎖定工作站(Windows 用 ``LockWorkStation``、Linux 用
  ``loginctl lock-session``、macOS 用 ``CGSession -suspend``),透過可注入的 ``driver``。
* :func:`plan_lock_session` ——純 planner:此 OS 上會如何執行鎖定,以及是否有預設可用
  (``{backend, argv, available}``)。
* :func:`wait_for_unlock` / :func:`wait_for_lock` ——輪詢 :func:`is_session_locked`
  直到狀態翻轉或逾時,``clock`` / ``sleep`` / ``probe`` 皆可注入以利確定性測試。
* :func:`classify_lock_transitions` ——純函式:把一連串鎖定狀態取樣化約為
  ``{event, locked}`` 鎖定 / 解鎖轉變的清單。

wait 系列重用的鎖定 probe 即 :mod:`session_guard` 的——Windows 的 ``OpenInputDesktop`` 檢查——
故 ``wait_for_unlock`` 是 ``ensure_interactive_session``(只會丟例外)的阻塞式搭檔。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        lock_session, wait_for_unlock, classify_lock_transitions,
    )

    # ... 無人值守執行結束 ...
    lock_session()                 # 鎖住機器

    # 等有人解鎖後才繼續
    if wait_for_unlock(timeout_s=600):
        run_next_stage()

    # 把取樣的鎖定狀態紀錄化約為事件
    classify_lock_transitions([False, True, True, False])
    # -> [{'event': 'lock', 'locked': True},
    #     {'event': 'unlock', 'locked': False}]

測試時(或任何主機)可傳入 ``driver`` / ``probe``:

.. code-block:: python

    locked = lock_session(driver=lambda: True)        # 不真正鎖定
    wait_for_unlock(probe=lambda: False)              # 已解鎖

執行器指令
----------

``AC_lock_session``(→ ``{locked}``)、``AC_plan_lock_session``(→ 計畫)、
``AC_wait_for_unlock``(``timeout`` / ``interval`` → ``{unlocked}``)與
``AC_classify_lock_transitions``(``states`` JSON 清單 → ``{events}``)。皆以對應的 ``ac_*``
MCP 工具(``ac_lock_session`` 為破壞性——會中斷 session;其餘為唯讀)及 Script Builder 指令
(位於 **Shell** 分類下)形式提供。
