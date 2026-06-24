可讀且可定址的無障礙樹(角色名稱 + 節點路徑)
=============================================

``dump_accessibility_tree`` 輸出的節點帶有平台的*原始*角色——在 Windows 上就是裸的
UI Automation ControlType id,例如按鈕是 ``"ControlType_50000"``。這既難以閱讀,且序列化後的
dump 不帶任何穩定的逐節點身分(UIA RuntimeId 需要存活的元素,而 dump 已將其丟棄)。
``ax_tree_walk`` 補上 dump 所缺、純粹且跨平台的後處理,可疊加在任何
``dump_accessibility_tree`` 輸出之上:

* :func:`control_type_name` / :func:`humanize_role` ——把 ControlType id(或
  ``"ControlType_NNNNN"`` / ``"NNNNN"`` 字串)轉成友善名稱,
* :func:`humanize_tree` ——回傳一份每個角色都已人性化的樹深拷貝,
* :func:`assign_node_paths` ——回傳一份深拷貝,為每個節點蓋上穩定的位置 ``path``
  (``"0.2.1"``)——作為 RuntimeId 身分的純粹替代,
* :func:`find_by_path` ——由 path 反解回節點。

純標準庫,針對 ``AXTreeNode`` 值運算;不存取裝置或後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (dump_accessibility_tree, humanize_tree,
                                 assign_node_paths, find_by_path, humanize_role)

    humanize_role("ControlType_50000")          # "Button"
    humanize_role(50004)                         # "Edit"

    tree = assign_node_paths(humanize_tree(dump_accessibility_tree()))
    # 每個節點現在都有可讀角色與 tree["attributes"]["path"]
    node = find_by_path(tree, "0.0.1")           # 由 path 重新解析節點

未知 id 與非 UIA 角色(``"AXApplication"``)原樣通過,故不會遺失任何資訊。path 對於給定的
樹形狀是穩定的,讓腳本 / agent 在 dump → 操作的往返中對某節點有確定性的把手。

執行器指令
----------

``AC_walk_tree``(``app_name`` / ``max_results``)以巢狀 dict 回傳已人性化、已蓋上 path 的樹
——即 ``AC_a11y_dump`` 的可讀對應版本。``AC_humanize_role``(``role``)回傳
``{"role": ...}``。兩者皆以唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Native UI**
分類下)形式提供。
