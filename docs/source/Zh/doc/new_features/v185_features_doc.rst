豐富剪貼簿格式——RTF 與 CSV/TSV
==============================

``rich_clipboard`` 已加入 ``CF_HTML`` 以便把豐富內容貼進 Word / Outlook,但仍缺少另外兩種
跨應用程式的剪貼簿格式:

* **RTF**（``"Rich Text Format"``)——幾乎每個豐富編輯器都接受、用於樣式貼上的格式。
  ``build_rtf`` / ``rtf_to_text`` 以純 Python 建立與剝除 RTF 控制字與 ``\uNNNN`` / ``\'XX``
  轉義,並具備完全可單元測試的往返。
* **CSV / TSV**（Excel 讀取的已註冊 ``"Csv"`` 格式)——``rows_to_csv`` / ``csv_to_rows`` 是對
  標準庫 ``csv`` 模組的薄包裝(可指定分隔符),讓表格能放上 / 讀下剪貼簿。

這些編解碼器與平台無關且可無頭測試;只有實際的剪貼簿 I/O 為 Win32(在其他平台拋出
``RuntimeError``,與基礎 ``clipboard`` 模組一致),且位元組傳輸是兩種格式共用的單一泛型輔助
函式。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (build_rtf, rtf_to_text, rows_to_csv,
                                 csv_to_rows, set_clipboard_rtf, set_clipboard_csv)

    rtf = build_rtf("Hello\nWorld")          # 最小的有效 RTF 文件
    rtf_to_text(rtf)                          # -> "Hello\nWorld"

    rows_to_csv([["a", "b"], ["1", "2"]])     # 'a,b\r\n1,2\r\n'
    csv_to_rows("a,b\r\n1,2\r\n")             # [["a", "b"], ["1", "2"]]

    set_clipboard_rtf("以樣式文字貼上我")        # Windows
    set_clipboard_csv([["Name", "Qty"], ["Pen", "3"]], delimiter="\t")  # TSV

``build_rtf`` 會轉義大括號 / 反斜線,把換行轉為 ``\par``,並把非 ASCII 字元轉為 ``\uNNNN?``
轉義(輸出為純 ASCII)。``set_clipboard_rtf`` / ``set_clipboard_csv`` 預設也會種入純文字,讓
純文字編輯器仍能貼上內容;``get_clipboard_rtf`` 回傳原始 RTF 字串(再餵給 ``rtf_to_text``),
``get_clipboard_csv`` 回傳列。

執行器指令
----------

``AC_set_clipboard_rtf`` / ``AC_get_clipboard_rtf`` / ``AC_set_clipboard_csv`` /
``AC_get_clipboard_csv``（set 取 ``text`` / ``rows`` 加 ``delimiter``)。皆以對應的 ``ac_*``
MCP 工具(set 為僅副作用、get 為唯讀)及 Script Builder 指令(位於 **Data** 分類下)形式提供。
