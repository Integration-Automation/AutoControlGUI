==========================================
新功能 (2026-06-19) — Plugin SDK
==========================================

第三方 pip 套件現在可透過 setuptools **entry point**(``je_auto_control.commands``
群組)宣告式地註冊新的 ``AC_*`` 執行器指令——把單體變成生態系(pytest /
Playwright 的成長方式)。AutoControl 於執行期探索它們;探索到的指令立即可
用於 JSON action 檔、socket server、排程器與 MCP。純標準庫
(``importlib.metadata``);走完整五層。

.. contents::
   :local:
   :depth: 2


撰寫外掛
========

外掛套件提供一個 entry point,其目標為回傳 ``{command_name: handler}``
對應的工廠函式::

    # 外掛的 pyproject.toml
    [project.entry-points."je_auto_control.commands"]
    my_pack = "my_pack.commands:provide"

    # my_pack/commands.py
    def provide():
        return {"AC_my_command": lambda **kw: {"ok": True}}


探索與載入
==========

::

    from je_auto_control import discover_plugins, load_plugins

    discover_plugins()      # 來自所有外掛的 {command_name: handler}
    load_plugins()          # 探索 + 註冊到執行器

壞掉的外掛會被略過(記錄),不致命。對應 ``AC_list_plugins``(探索名稱)
/ ``AC_load_plugins``(探索 + 註冊)以及 ``ac_list_plugins`` /
``ac_load_plugins``。entry-point 來源可注入,因此探索能在不安裝真實外掛
的情況下單元測試。這是既有執行期路徑載入器的宣告式、具命名空間的對應物。
