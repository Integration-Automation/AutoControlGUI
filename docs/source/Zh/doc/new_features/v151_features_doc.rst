標準化 Computer-Use 動作結構
============================

``tool_use_schema`` 把 AC_* 命令*簽章*匯出為工具定義,``coordinate_space`` 縮放模型網格——但兩者都不*正規化進來的
動作酬載*。Anthropic 的 computer-use 工具發出 ``{action:"left_click", coordinate:[x,y]}``,OpenAI 的 CUA 發出
``{type:"click", x, y, button}``——先前沒有把這些異質形狀對應到標準動作、再對應到可執行 AC_* 命令的轉接器,
整合者只能手寫膠水程式。

純標準函式庫的字典對應(選用 ``scale`` callable 套用座標空間縮放),完全可無頭測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (from_anthropic, from_openai_cua, to_ac_command,
                                 canonical_action)

    # Anthropic agent 輸出 -> 標準 -> 可執行 AC 動作。
    canonical = from_anthropic({"action": "left_click", "coordinate": [120, 80]})
    command = to_ac_command(canonical)
    # -> ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 120, "y": 80}]

    # OpenAI CUA,含 模型->實體 座標縮放。
    cmd = to_ac_command(from_openai_cua({"type": "scroll", "x": 5, "y": 6,
                                         "scroll_y": 120}),
                        scale=lambda x, y: (x * 2, y * 2))

``from_anthropic`` / ``from_openai_cua`` 把各供應商酬載對應為標準 ``{type, x, y, text, …}``(click、double/right/
middle click、move、type、key、scroll、screenshot)。``to_ac_command`` 把標準動作對應為 ``[command_name, params]``
AC 動作(``AC_click_mouse`` / ``AC_set_mouse_position`` / ``AC_write`` / ``AC_hotkey`` / ``AC_mouse_scroll`` /
``AC_screenshot``),並對座標套用 ``scale``;無法對應的類型會丟出 ``AutoControlActionException``。``canonical_action``
直接建立標準字典。

執行器命令
----------

``AC_cua_command`` 從 ``source``(``anthropic`` / ``openai`` / ``canonical``)正規化 ``payload`` 並回傳
``{canonical, command}``。它以 MCP 工具 ``ac_cua_command`` 以及 Script Builder 中 **Native UI** 分類下的命令提供。
