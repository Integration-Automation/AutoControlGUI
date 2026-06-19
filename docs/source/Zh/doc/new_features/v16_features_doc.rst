==========================================
新功能 (2026-06-19) — WCAG 2.2 稽核引擎
==========================================

無障礙稽核新增 **WCAG 2.2 / EN 301 549 成功準則層**:每個缺陷都會標註其
違反的 WCAG 準則(編號 + 名稱 + 符合等級 + 影響程度),並新增一條 WCAG
2.2 規則——**目標尺寸(最小),SC 2.5.8**——由元素 bounds 計算。產出的
符合度報告可對應 EN 301 549,作為無障礙合規證據(歐洲無障礙法
EAA 自 2025 年 6 月起強制)。純標準庫;走完整五層。

.. contents::
   :local:
   :depth: 2


符合度稽核
==========

::

    from je_auto_control import wcag_audit

    report = wcag_audit(level="AA")          # 即時 a11y 樹
    report = wcag_audit(elements=els,        # 或提供 元素/顏色/文字
                        contrast_pairs=pairs, texts=ocr_texts, level="AA")

    report["conformant"]      # 在要求等級下無任何發現時為 True
    report["by_criterion"]    # {"1.4.3 Contrast (Minimum)": 2, ...}
    report["findings"]        # 每筆標註 {sc, criterion, level, impact, ...}

發現會依要求的符合等級(``A`` / ``AA`` / ``AAA``)過濾。對應的成功準則:

* **1.1.1 / 4.1.2** — 互動元素沒有可存取名稱。
* **1.4.3 Contrast (Minimum)** — 前景/背景對比低於門檻。
* **1.4.10 Reflow** — 文字被裁切 / 截斷。
* **2.5.8 Target Size (Minimum)** — *2.2 新增*:指標目標小於 24x24 px。


目標尺寸規則
============

``audit_target_size(elements, min_px=24)`` 會標記 bounds 任一邊小於
``min_px`` 的互動元素(尺寸未知者略過)。``tag_issue(issue)`` 會把任何
基礎 ``AuditIssue`` 標註其成功準則,因此既有稽核也能取得 SC 標註。

對應 ``AC_wcag_audit`` / ``ac_wcag_audit``(以及 facade 上的 ``wcag_audit``
/ ``audit_target_size``)。
