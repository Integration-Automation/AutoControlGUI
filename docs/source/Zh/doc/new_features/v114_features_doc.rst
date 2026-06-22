GNU gettext 目錄 I/O(.po / .mo)
===============================

本專案已有 ``i18n_test``(偽在地化、目錄佔位符檢查)與 ``message_format``(ICU 渲染),但沒有讀取*事實標準*
翻譯格式 GNU gettext ``.po`` / ``.mo`` 的工具。本功能解析 ``.po`` 文字(上下文、複數、多行字串、跳脫、
``Plural-Forms`` 標頭)、編譯二進位 ``.mo``(與 Python 內建 ``gettext`` 讀取的小端格式相同),並提供
``gettext`` / ``ngettext`` / ``pgettext`` 查詢。

純標準函式庫(``re`` / ``struct`` / 以 ``gettext.c2py`` 處理複數運算式);不匯入 ``PySide6``。解析與編譯皆為
純資料進/資料出,因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import parse_po, read_mo, GettextCatalog

    catalog = parse_po(po_text)
    catalog.gettext("Hello")                 # 'Hola'
    catalog.ngettext("file", "files", 3)     # 'archivos'
    catalog.pgettext("menu", "Open")         # 'Abrir'

    mo_bytes = catalog.compile_mo("out/messages.mo")   # 或 .to_mo_bytes()
    same = read_mo(mo_bytes)                  # 可往返,含複數規則

    # 以程式手動建立
    cat = GettextCatalog()
    cat.add("apple", ["pomme", "pommes"], plural_id="apples")

``gettext`` 回傳翻譯(未翻譯時回傳原始 ``msgid``);``ngettext`` 評估目錄的 ``Plural-Forms`` 運算式
(透過 ``gettext.c2py``)以為 ``n`` 選擇正確形式;``pgettext`` 加入消歧上下文。``to_mo_bytes`` / ``compile_mo``
產生符合標準、可被 Python 內建 ``gettext.GNUTranslations`` 載入的 ``.mo``,而 ``read_mo`` / ``read_mo_file``
可反向解析(小端或大端)。

執行器命令
----------

``AC_gettext_translate`` 解析內嵌 ``.po`` 字串並回傳某 ``msgid``(可帶 ``context``)的 ``{text}``;
``AC_gettext_ngettext`` 回傳計數 ``n`` 的複數正確 ``{text}``。兩者皆以 MCP 工具(``ac_gettext_translate`` /
``ac_gettext_ngettext``)以及 Script Builder 中 **Data** 分類下的命令提供。
