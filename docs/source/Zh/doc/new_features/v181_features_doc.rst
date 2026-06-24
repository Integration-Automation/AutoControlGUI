擴充 UIA 控制模式(展開 / 選取 / 範圍 / 捲動)
===============================================

無障礙後端原本只提供四種控制模式——Value、Invoke、Toggle 與唯讀的 Grid dump。這使得自動化
最常遇到的控制項無法以其*原生*模式驅動:樹節點無法展開、清單 / 下拉項目無法選取
(SelectionItemPattern)、滑桿無法設定(RangeValuePattern)、控制項無法捲入視野
(ScrollItemPattern)——這些只能退回脆弱的像素猜測。``control_patterns`` 在既有的無障礙後端
ABC 之上補上這些物件層級動作。

每個函式都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派(與無障礙模組
其餘部分相同的接縫),因此無頭核心可在任何平台透過注入 fake backend 單元測試;真正的
UI Automation 呼叫位於 Windows 後端(ExpandCollapse / SelectionItem / RangeValue / ScrollItem
模式)。未實作某模式的後端會拋出 ``AccessibilityNotAvailableError``。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (expand_control, collapse_control,
                                 control_expand_state, select_control_item,
                                 control_range, set_control_range,
                                 scroll_control_into_view)

    expand_control(name="Documents", role="treeitem")     # 展開樹節點
    select_control_item(name="Option B")                  # 選取清單/下拉項目
    set_control_range(75, name="Volume")                  # 設定滑桿
    print(control_range(name="Volume"))   # {"value": 75.0, "minimum": 0, "maximum": 100}
    scroll_control_into_view(name="Row 200")              # 把某列帶上螢幕

全部以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位控制項(與既有
``control_invoke`` / ``control_toggle`` 相同)。展開/選取/捲動/設定動作回傳 ``bool``;
``control_expand_state`` 回傳 ``expanded`` / ``collapsed`` / ``partial`` / ``leaf``(或
``None``);``control_range`` 回傳 ``{value, minimum, maximum}``(或 ``None``)。

執行器指令
----------

``AC_expand_control`` / ``AC_collapse_control`` / ``AC_control_expand_state`` /
``AC_select_control_item`` / ``AC_control_range`` / ``AC_set_control_range`` /
``AC_scroll_control_into_view``。皆以對應的 ``ac_*`` MCP 工具(動作類為破壞性、讀取類為唯讀)
及 Script Builder 指令(位於 **Native UI** 分類下)形式提供。
