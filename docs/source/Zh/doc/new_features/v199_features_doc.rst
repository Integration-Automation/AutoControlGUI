舊式控制項的 MSAA 橋接(LegacyIAccessible)
==========================================

許多舊式 Win32 / MFC / Delphi 控制項透過現代 UI Automation 模式**完全不提供有用資訊**——
``control_get_value`` / ``control_invoke`` / ``control_toggle`` 都回 None 或毫無作用——但它們透過
MSAA ``IAccessible`` 橋接卻有完整描述:Name、Value、Description、Role、State,以及一個
**DefaultAction**。``legacy_accessible`` 就是那個最後手段的後備:仍能讀取這些資訊並觸發預設動作,
讓大量舊應用程式得以自動化。

* :func:`legacy_info` ——MSAA 欄位 ``{name, value, description, default_action, role, state}``,
* :func:`legacy_default_action` ——觸發控制項的預設動作。

每個都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可透過注入 fake
backend 進行無頭測試;真正的 ``LegacyIAccessiblePattern`` 呼叫位於 Windows 後端。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (legacy_info, legacy_default_action,
                                 control_invoke)

    # 現代模式撲空?退回 MSAA:
    if not control_invoke(name="Apply"):
        info = legacy_info(name="Apply")          # {"default_action": "Press", ...}
        legacy_default_action(name="Apply")        # 觸發 MSAA 預設動作

控制項以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位(與其他原生控制動作相同)。
``legacy_info`` 回傳 MSAA 資訊字典(``role`` / ``state`` 為原始 MSAA 數字),找不到控制項或模式
則回傳 ``None``;``legacy_default_action`` 回傳 ``bool``。

執行器指令
----------

``AC_legacy_info``(``{found, info}``)與 ``AC_legacy_default_action``。皆以對應的 ``ac_*`` MCP
工具(info 為唯讀、動作為破壞性)及 Script Builder 指令(位於 **Native UI** 分類下)形式提供。
