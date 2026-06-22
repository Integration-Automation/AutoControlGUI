==========================================
新功能 (2026-06-19) — Set-of-Marks 疊圖
==========================================

現代 GUI agent 在看到「畫上**編號方框**的截圖 + ``id -> bbox`` 圖例」時
定位會可靠得多(Set-of-Marks prompting):模型挑一個*編號*,而不是猜
像素座標。本功能把 AutoControl 既有的元素來源轉成這種「先標號、再挑號」
的兩階段流程,並把選到的編號解析回一次點擊。純標準庫 + Pillow(已是相依);
走完整五層。

.. contents::
   :local:
   :depth: 2


標號與圖例
==========

::

    from je_auto_control import mark_elements, render_marks, resolve_mark

    marks = mark_elements(elements)   # [{id, bbox, center, role, text}, ...]
    legend = [(m["id"], m["text"]) for m in marks]
    annotated_png = render_marks(screenshot_png_bytes, marks)
    chosen = resolve_mark(marks, 3)   # 模型挑中的元素

``mark_elements`` 會為每個有有效 bounds 的元素指派 ``1..N`` 並記錄中心點;
``render_marks`` 在 PNG 上畫出編號紅框;``resolve_mark`` 把編號對應回該
標記。這些都是純函式,可用合成元素做單元測試。


即時「標號後點擊」迴圈
======================

::

    from je_auto_control import mark_screen, mark_click

    result = mark_screen(render_path="marked.png")   # 為即時 a11y 樹標號
    # ... 把 result["marks"] + marked.png 餵給 VLM,取回一個編號 ...
    mark_click(3)                                     # 點擊第 3 號標記

``mark_screen`` 為即時 accessibility 元素標號(並可另存編號方框疊圖截圖),
並快取這些標記;``mark_click`` 從快取解析編號並點擊該元素中心。對應
``AC_mark_screen`` / ``AC_mark_click``(以及 ``ac_mark_screen`` /
``ac_mark_click``)。
