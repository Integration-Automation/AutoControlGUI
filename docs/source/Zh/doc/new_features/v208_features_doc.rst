即時 IME 狀態以利安全的 CJK 輸入
================================

在 IME(輸入法)*組字中*對 CJK / 日文 / 韓文欄位輸入並不安全:候選字尚未送出,故讀回欄位會得到
半成形的字,而下一個按鍵會編輯組字而非欄位。``text_unicode``(``VK_PACKET``)對此一無所知。
``ime_state`` 暴露即時的組字與轉換狀態,讓流程能在讀取或操作前等待 IME 送出。

* :func:`ime_state` ——聚焦視窗 IME 的 ``{open, composing, composition, conversion,
  conversion_flags}``,透過可注入的 ``reader``。
* :func:`is_composing` ——當 IME 有尚未送出的組字時回傳 ``True``。
* :func:`wait_for_composition_commit` ——阻塞直到組字結束(或逾時),``clock`` / ``sleep`` /
  ``reader`` 皆可注入。
* :func:`decode_conversion_mode` ——純函式:把 IMM32 ``IME_CMODE_*`` 轉換位元遮罩解碼為
  ``{native, katakana, full_shape, roman, char_code}``。

預設 ``reader`` 以唯讀方式查詢 Windows IMM32(``ImmGetContext`` / ``ImmGetOpenStatus`` /
``ImmGetConversionStatus`` / ``ImmGetCompositionStringW``);所有解碼 / 等待邏輯都透過可注入接縫
執行,故能在沒有 IME 的情況下完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        ime_state, is_composing, wait_for_composition_commit,
    )

    # 讀取 CJK 欄位前,先確認 IME 已送出
    if wait_for_composition_commit(timeout_s=3):
        value = read_field()

    is_composing()   # 候選字仍在畫面上時為 True
    ime_state()      # {'open': True, 'composing': True, 'composition': 'あ', ...}

測試時(或任何非 Windows 主機)可傳入 ``reader`` ——一個
``() -> {open, conversion, composition}``:

.. code-block:: python

    busy = lambda: {"open": True, "conversion": 0, "composition": "あ"}
    is_composing(reader=busy)              # True
    ime_state(reader=busy)["composition"]  # 'あ'

執行器指令
----------

``AC_ime_state``(→ 完整狀態)、``AC_is_composing``(→ ``{composing}``)、
``AC_wait_for_composition_commit``(``timeout`` / ``interval`` → ``{committed}``)
與 ``AC_decode_conversion_mode``(``flags`` → 解碼後的模式)。皆以對應的唯讀 ``ac_*`` MCP 工具
及 Script Builder 指令(位於 **Shell** 分類下)形式提供。
