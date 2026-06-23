豐富剪貼簿——HTML(CF_HTML)
=============================

基礎 ``clipboard`` 模組只處理純文字(``CF_UNICODETEXT``)與影像(``CF_DIB``)。將*格式化*內容貼進 Word /
Outlook / 富文字編輯器需要 ``CF_HTML`` 格式,其 ``Version / StartHTML / EndHTML / StartFragment /
EndFragment`` **位元組偏移**標頭以手寫極易出錯。``build_cf_html`` / ``parse_cf_html`` 以純 Python 計算與還原
該標頭(完整單元測試的往返,且在多位元組 UTF-8 下正確),而 ``set_clipboard_html`` / ``get_clipboard_html``
將其包裝於 Win32 剪貼簿之上。

位元組偏移運算與平台無關且可無頭測試;只有實際的剪貼簿 I/O 為 Windows(在其他平台丟出 ``RuntimeError``,
與基礎模組一致)。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (build_cf_html, parse_cf_html,
                                 set_clipboard_html, get_clipboard_html)

    set_clipboard_html("<b>Bold</b> and <i>italic</i>",
                       fragment_plaintext="Bold and italic")   # Windows
    html = get_clipboard_html()                                 # Windows

    # 純函式在任何平台皆可用(例如預先建立 payload):
    payload = build_cf_html("<p>hello</p>")     # bytes,有效 CF_HTML
    assert parse_cf_html(payload) == "<p>hello</p>"

``build_cf_html`` 回傳偏移精確指向片段的有效 ``CF_HTML`` UTF-8 位元組;``parse_cf_html`` 從 bytes 或文字還原片段
(優先用註解標記,退而用位元組偏移)。``set_clipboard_html`` 也會以 ``fragment_plaintext`` 設定純文字,讓忽略
HTML 的程式仍能貼上內容。

執行器命令
----------

``AC_set_clipboard_html``(``html`` / ``fragment_plaintext`` → ``{set, length}``)與 ``AC_get_clipboard_html``
(→ ``{found, html}``)。它們以 MCP 工具 ``ac_set_clipboard_html`` / ``ac_get_clipboard_html`` 以及 Script
Builder 中 **Data** 分類下的命令提供。
