==========================================
新功能 (2026-06-19) — i18n / l10n 測試
==========================================

三項可互相搭配的純標準庫國際化 / 在地化測試輔助工具,走完整五層
(facade、``AC_*`` 執行器指令、MCP 工具、Script Builder)。

.. contents::
   :local:
   :depth: 2


偽在地化(Pseudo-localization)
==============================

在真正的翻譯出現*之前*,先為 UI 字串加上重音與填充(保留佔位符),以
揪出寫死的字串並預先對版面施壓::

    from je_auto_control import pseudo_localize, pseudo_localize_catalog

    pseudo_localize("Hello {name}")        # "⟦Hèllo {name}········⟧"
    pseudo_localize_catalog({"save": "Save", "cancel": "Cancel"})

佔位符(``{name}`` / ``{{x}}`` / ``%s`` / ``%d``)會原樣保留;``expansion``
控制填充比例;``⟦…⟧`` 括號讓截斷一眼可見。對應 ``AC_pseudo_localize`` /
``ac_pseudo_localize``。畫面中未被加重音(未翻譯)的字串,代表它是未外部化
的寫死文字。


文字溢位偵測
============

標記估計寬度超過其元件邊界的文字——在地化的頭號 bug(德文/芬蘭文會膨脹
30–50%)。由 AutoControl 既有讀取的 accessibility 邊界計算::

    from je_auto_control import check_overflow

    issues = check_overflow(elements, avg_char_px=7.0)
    # [{"text": "...", "width": 40, "required_px": 400.0, "overflow_px": 360.0}]

寬度以 ``len(text) * avg_char_px`` 估計(決定性啟發式)。對應
``AC_check_overflow`` / ``ac_check_overflow``(未提供 ``elements`` 時使用
即時 a11y 樹)。


翻譯目錄完整性
==============

把翻譯目錄與基準語系比對:缺漏 / 多餘 / 空白鍵與佔位符不一致——可作為防止
空白 UI 的 CI 閘::

    from je_auto_control import check_catalog

    report = check_catalog(base_locale, target_locale)
    report["missing"]               # target 中缺漏的鍵
    report["placeholder_mismatch"]  # 例如 target 漏掉 "{count}"

對應 ``AC_check_catalog`` / ``ac_check_catalog``。
