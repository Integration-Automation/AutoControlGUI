=====================
新功能 (2026-04)
=====================

本頁說明 2026 年 4 月加入的新功能。每一項新功能都同時提供 **無 GUI 的
Python API** 與 **對應的 GUI 介面**，並已連接到 executor，可從 JSON 腳
本、socket server、REST API 及 CLI 直接使用，無需撰寫額外 Python 程式
碼。

.. contents::
   :local:
   :depth: 2


剪貼簿 (Clipboard)
==================

程式碼呼叫::

   import je_auto_control as ac
   ac.set_clipboard("hello")
   text = ac.get_clipboard()

Action-JSON 指令::

   [["AC_clipboard_set", {"text": "hello"}]]
   [["AC_clipboard_get", {}]]

平台後端：Windows (ctypes + Win32)、macOS (``pbcopy`` / ``pbpaste``)、
Linux (``xclip`` 或 ``xsel``)。若無可用後端會拋出 ``RuntimeError``。


試跑 / 逐步除錯 (Dry-run / Step Debug)
======================================

無副作用執行 action 列表，方便驗證 JSON 腳本::

   from je_auto_control.utils.executor.action_executor import executor
   record = executor.execute_action(actions, dry_run=True)

``step_callback`` 可在每一條 action 執行前收到通知::

   executor.execute_action(actions, step_callback=lambda a: print(a))

CLI::

   python -m je_auto_control.cli run script.json --dry-run


全域熱鍵 (Windows)
==================

綁定系統級熱鍵到 action-JSON 腳本::

   from je_auto_control import default_hotkey_daemon
   default_hotkey_daemon.bind("ctrl+alt+1", "scripts/greet.json")
   default_hotkey_daemon.start()

支援的修飾鍵：``ctrl``、``alt``、``shift``、``win`` / ``super`` /
``meta``。按鍵：英文字母、數字、``f1``–``f12``、方向鍵、``space``、
``enter``、``tab``、``escape`` 等。

macOS 與 Linux 目前在 ``start()`` 會拋出 ``NotImplementedError`` ──
採 Strategy pattern，未來可擴充對應後端。

GUI：**全域熱鍵** 分頁。


事件觸發器 (Triggers)
=====================

輪詢式觸發器，偵測到畫面或狀態變化時執行腳本::

   from je_auto_control import default_trigger_engine, ImageAppearsTrigger
   default_trigger_engine.add(ImageAppearsTrigger(
       trigger_id="", script_path="scripts/click_ok.json",
       image_path="templates/ok_button.png", threshold=0.85,
       repeat=True,
   ))
   default_trigger_engine.start()

可用類型：

- ``ImageAppearsTrigger`` — 螢幕上偵測模板影像
- ``WindowAppearsTrigger`` — 視窗標題包含子字串
- ``PixelColorTrigger`` — 某座標像素顏色在容差內
- ``FilePathTrigger`` — 監看檔案 mtime 變化

GUI：**事件觸發器** 分頁。


Cron 排程
=========

五欄位 cron (``minute hour day-of-month month day-of-week``)，支援
``*``、逗號列表、``*/step`` 步進、``start-stop`` 範圍::

   from je_auto_control import default_scheduler
   job = default_scheduler.add_cron_job(
       script_path="scripts/daily.json",
       cron_expression="0 9 * * 1-5",   # 週一到週五 09:00
   )
   default_scheduler.start()

interval 與 cron 排程可同時存在，可由 ``job.is_cron`` 判斷類型。
GUI：**排程器** 分頁新增 cron/interval 切換。


外掛載入器 (Plugin Loader)
==========================

外掛檔案為任何定義頂層 ``AC_*`` callable 的 ``.py``，每個都會成為新的
executor 指令::

   # my_plugins/greeting.py
   def AC_greet(args=None):
       return f"hello, {args['name']}"

::

   from je_auto_control import (
       load_plugin_directory, register_plugin_commands,
   )
   commands = load_plugin_directory("my_plugins/")
   register_plugin_commands(commands)

GUI：**外掛** 分頁，可選擇目錄一鍵載入。

.. warning::
   外掛檔案會直接執行任意 Python 程式。請務必只載入自己信任的目錄。


REST API 伺服器
===============

純 stdlib HTTP server，公開 executor 與 scheduler::

   from je_auto_control import start_rest_api_server
   server = start_rest_api_server(host="127.0.0.1", port=9939)

端點：

- ``GET /health``
- ``GET /jobs``
- ``POST /execute`` (body: ``{"actions": [...]}``)

GUI：**Socket 伺服器** 分頁新增獨立的 REST 區塊。

.. note::
   預設綁定 ``127.0.0.1`` (符合 CLAUDE.md 規範)。只有在網路邊界已做好
   身分驗證時才綁定 ``0.0.0.0``。


CLI 子指令介面
==============

以 headless API 為基礎的輕量 CLI::

   python -m je_auto_control.cli run script.json
   python -m je_auto_control.cli run script.json --var name=alice --dry-run
   python -m je_auto_control.cli list-jobs
   python -m je_auto_control.cli start-server --port 9938
   python -m je_auto_control.cli start-rest --port 9939

``--var name=value`` 優先以 JSON 解析 (``count=10`` 會變 int)，失敗時
當作字串。


GUI 多語系
==========

可透過 **Language** 選單即時切換。內建語言包：

- English
- 繁體中文 (Traditional Chinese)
- 简体中文 (Simplified Chinese)
- 日本語 (Japanese)

執行期可註冊額外語言::

   from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
       language_wrapper,
   )
   language_wrapper.register_language("French", {"menu_file": "Fichier", ...})

缺少的 key 會退回英文，讓新功能未翻譯前仍可正常顯示。


可關閉分頁 + 選單列
===================

主視窗改為 ``QMainWindow`` + 選單列：

- **File** → 開啟腳本 / 結束
- **View → Tabs** → 每個分頁可勾選顯示或隱藏
- **Tools** → 啟動熱鍵 / 排程 / 觸發器服務
- **Language** → 切換語言
- **Help** → 關於

點擊分頁的 ✕ 即可關閉，之後可從 *View → Tabs* 恢復。


OCR 螢幕文字辨識
================

以 Tesseract 為後端的文字定位。適用於沒有穩定 Accessibility 名稱、也
不方便擷取模板影像的按鈕或標籤::

   import je_auto_control as ac

   matches = ac.find_text_matches("Submit")
   cx, cy = ac.locate_text_center("Submit")
   ac.click_text("Submit")
   ac.wait_for_text("載入完成", timeout=15.0)

若 Tesseract 不在 ``PATH`` 中::

   ac.set_tesseract_cmd(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

Action-JSON 指令：``AC_locate_text``、``AC_click_text``、
``AC_wait_text``。


Accessibility 元件搜尋
======================

透過作業系統無障礙樹查詢控制項（Windows UIA 透過 ``uiautomation``；
macOS AX），支援依名稱 / 角色 / 應用程式過濾::

   import je_auto_control as ac

   elements = ac.list_accessibility_elements(app_name="Calculator")
   ok = ac.find_accessibility_element(name="OK", role="Button")
   ac.click_accessibility_element(name="OK", app_name="Calculator")

當前平台若沒有可用後端會拋出 ``AccessibilityNotAvailableError``。
Action-JSON 指令：``AC_a11y_list``、``AC_a11y_find``、
``AC_a11y_click``。GUI：**Accessibility** 分頁。


VLM（AI）元件定位
=================

當模板匹配與 Accessibility 都無法找到目標時，可用自然語言描述元件，
交給視覺語言模型回傳像素座標::

   import je_auto_control as ac

   x, y = ac.locate_by_description("綠色的 Submit 按鈕")
   ac.click_by_description(
       "Cookie 橫幅中的『全部接受』按鈕",
       screen_region=[0, 800, 1920, 1080],   # 可選：只在此區域搜尋
   )

後端（延遲載入，import ``je_auto_control`` 時不會引入）：

- Anthropic (``anthropic`` SDK，``ANTHROPIC_API_KEY``)
- OpenAI (``openai`` SDK，``OPENAI_API_KEY``)

環境變數（金鑰不會被記錄或寫入磁碟）：

- ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``
- ``AUTOCONTROL_VLM_BACKEND=anthropic|openai``
- ``AUTOCONTROL_VLM_MODEL=<model-id>``

Action-JSON 指令：``AC_vlm_locate``、``AC_vlm_click``。GUI：
**AI Locator** 分頁。


執行歷史 + 錯誤截圖附件
=======================

排程器、觸發器、熱鍵守護程序、REST API 與 GUI 手動回放的每一次執行
都會被寫入 ``~/.je_auto_control/history.db``（SQLite）。失敗時會自動
擷取螢幕截圖並附到該筆紀錄上::

   from je_auto_control import default_history_store

   for run in default_history_store.list_runs(limit=20):
       print(run.id, run.source, run.status, run.artifact_path)

截圖檔存於 ``~/.je_auto_control/artifacts/``，相關紀錄被 prune 或整個
歷史被清除時會一併刪除。GUI：**Run History** 分頁 — 雙擊截圖欄位可開
啟 OS 預覽。
