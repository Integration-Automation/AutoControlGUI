============================================
新功能 (2026-06-19) — 視覺回歸與狀態機
============================================

兩個早已存在、卻從未接上其餘各層的 headless 核心,現在成為一級功能:
**黃金影像視覺回歸**與**宣告式有限狀態機**執行器。兩者都提供 facade
re-export、``AC_*`` 執行器指令、MCP 工具與 Script Builder 項目,並有
headless 測試(PIL 影像 / spec 以注入方式提供,完全不需真實螢幕)。

.. contents::
   :local:
   :depth: 2


視覺回歸(黃金影像)
====================

擷取基準圖,之後在畫面偏離時讓該次執行失敗——等同於截圖版的 snapshot
測試::

    from je_auto_control import take_golden, compare_to_golden

    take_golden("goldens/login.png")                      # 建立基準
    result = compare_to_golden("goldens/login.png", tolerance=0.5)
    if not result.matched:
        result.write_diff("goldens/login.diff.png")
        print(result.summary)

``compare_to_golden`` 回傳 ``DiffResult``(``matched``、``diff_pct``、
``differing_pixels``、標示差異的 ``diff_image``);``tolerance`` 是允許
差異的像素百分比,``per_pixel_threshold`` 可忽略各通道的細微雜訊。
``MaskRegion`` 可排除動畫 / 易變區域。純 PIL——不需 OpenCV / SciPy。

執行器指令:

* ``AC_take_golden`` — 擷取並存基準圖(可選 ``region``)。
* ``AC_assert_visual`` — 把畫面與黃金影像比對,不符即拋例外(可存
  ``diff_path``)。**首跑**(基準不存在)時會擷取基準並通過,除非
  ``create_if_missing`` 設為 false。


有限狀態機
==========

把腳本當成宣告式狀態機來驅動——對於畫面流程自動化,比巢狀 loop / if
更清楚::

    from je_auto_control import run_state_machine

    spec = {
        "initial": "login",
        "states": {
            "login": {"on_enter": [["AC_click_text", {"text": "Sign in"}]],
                       "transitions": [{"go_to": "home", "after": 1.0}]},
            "home": {"final": True},
        },
    }
    result = run_state_machine(spec)   # {final_state, steps, elapsed_s}

每個狀態的 ``on_enter`` 動作會透過執行器執行;transition 依 guard 觸發
(延遲 ``after``、``if_var_eq`` 或呼叫端 predicate)。``max_steps`` 與
``global_timeout_s`` 限制執行,使其不會無限迴圈。

執行器指令:``AC_run_state_machine``(``spec`` dict 可原樣經 JSON 動作檔 /
socket server / MCP 傳遞)。
