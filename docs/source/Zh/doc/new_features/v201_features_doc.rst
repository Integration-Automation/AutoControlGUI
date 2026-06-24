容器選取 + 檢視切換(Selection / MultipleView)
==============================================

``select_control_item``(SelectionItemPattern)選取*單一*項目;容器層級的 ``SelectionPattern``
回答自然的後續問題——listbox / grid / tab 中**目前選了什麼**,以及**是否可多選?**——這正是選取
之後的斷言目標。``MultipleViewPattern`` 在控制項的各檢視之間切換(檔案總管的清單 / 詳細資料 /
並排 / 縮圖),這是個常見前置條件,否則就得靠脆弱的選單點擊。

* :func:`get_selection` ——``{items, can_select_multiple, is_required}``,
* :func:`list_views` ——``{current, views: [...]}``,
* :func:`set_view` ——切換到具名的檢視。

每個都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可透過注入 fake
backend 進行無頭測試;真正的 UIA 呼叫位於 Windows 後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import get_selection, list_views, set_view

    get_selection(name="File List")
    # {"items": ["report.pdf", "notes.txt"], "can_select_multiple": True,
    #  "is_required": False}

    list_views(name="File List")
    # {"current": "Details", "views": ["List", "Details", "Tiles"]}
    set_view("Tiles", name="File List")        # 切換檢視

控制項以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位(與其他原生控制動作相同)。
``get_selection`` / ``list_views`` 回傳其字典(找不到控制項或模式則為 ``None``);``set_view``
回傳 ``bool``(具名檢視不支援時為 False)。

執行器指令
----------

``AC_get_selection``(``{found, selection}``)、``AC_list_views``(``{found, views}``)與
``AC_set_view``(``view``)。皆以對應的 ``ac_*`` MCP 工具(讀取類為唯讀、``set_view`` 為破壞性)
及 Script Builder 指令(位於 **Native UI** 分類下)形式提供。
