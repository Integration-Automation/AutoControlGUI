JSON Pointer、Patch 與 Merge Patch
==================================

``jsonpath`` 查詢是唯讀的,而 ``approval`` 以相等性比較整份產物,但沒有任何東西能定址單一位置、
計算結構化*差異*,或對 JSON 文件套用部分更新。本功能補上填補此缺口的三個 IETF 原語:

* **RFC 6901 JSON Pointer** —— 定址單一位置(``/a/b/0``)。
* **RFC 6902 JSON Patch** —— 有序的操作清單(add/remove/replace/move/copy/test);另含
  ``make_patch`` 以對兩份文件取差異。
* **RFC 7386 JSON Merge Patch** —— 遞迴合併,其中 ``null`` 代表刪除。

適用於設定漂移偵測、流程中的部分更新、HTTP PATCH 內容,以及回報 golden-master 差異。純標準
函式庫(``json`` + ``copy``);完全具決定性;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        resolve_pointer, make_patch, apply_patch, merge_patch,
        make_merge_patch, set_pointer, remove_pointer)

    doc = {"user": {"name": "Jo", "tags": ["a", "b"]}}

    resolve_pointer(doc, "/user/tags/0")          # "a"

    patch = make_patch(doc, {"user": {"name": "Joe", "tags": ["a"]}})
    # [{"op": "replace", "path": "/user/name", "value": "Joe"},
    #  {"op": "remove",  "path": "/user/tags/1"}]
    apply_patch(doc, patch)                        # 更新後的文件

    merge_patch({"a": 1, "b": 2}, {"b": None, "c": 3})   # {"a": 1, "c": 3}

``apply_patch`` 是**原子的** —— 它套用在副本上,只有完全成功才回傳,因此失敗的 ``test`` 操作
會讓原始文件保持不變。六個操作完全遵循 RFC 6902(``add`` 會插入陣列、``test`` 做深度相等且讓
``true`` 與 ``1`` 相異、``move`` 拒絕把值移入自身子節點)。``set_pointer`` / ``remove_pointer``
是純粹的單一位置便利函式。``merge_patch`` 遵循 RFC 7386(``null`` 值刪除該鍵;非物件的 patch
整體取代)。

執行器命令
----------

``AC_resolve_pointer``(``{value}``)、``AC_apply_json_patch``(``{result}``)、
``AC_make_json_patch``(``{patch}``)與 ``AC_merge_patch``(``{result}``)接受物件或 JSON 字串
作為輸入。每個亦以 MCP 工具(``ac_resolve_pointer`` / ``ac_apply_json_patch`` /
``ac_make_json_patch`` / ``ac_merge_patch``)以及 Script Builder 中 **Data** 分類下的命令提供。
