==========================================
新功能 (2026-06-17) — 自動化工具箱
==========================================

三十多個自動化原語,涵蓋輸入擬真、視覺、流程控制、觸發器、視窗管理與
檔案安全——另加「可還原(資源回收桶)刪除」與「錄製編輯器 Undo」。每項
功能都附帶 headless Python API、``AC_*`` 執行器指令,以及視覺化 Script
Builder 項目。視覺與視窗功能的 geometry / IO 操作皆可注入,因此邏輯無需
真實螢幕或視窗即可完整單元測試。

.. contents::
   :local:
   :depth: 2


擬人化輸入
==========

像真人一樣移動游標與打字——適合 demo、擬真自動化,以及會偵測機械式時序
的應用。路徑與延遲產生器在給定 ``seed`` 時為純函式且可重現::

    from je_auto_control import move_mouse_humanized, type_text_humanized

    # 曲線、eased Bezier 路徑,含 overshoot 與 jitter。
    move_mouse_humanized(800, 400, duration_s=0.5,
                         motion=None, seed=None)

    # 逐字打字,每字隨機微延遲。
    type_text_humanized("Hello, world", base_delay=0.05,
                        jitter=0.04, pause_chance=0.1, seed=1)

執行器指令:``AC_human_move``、``AC_human_type``。


視覺
====

* **VLM 自然語言斷言** — ``assert_by_description("a green success toast")``
  以視覺語言模型判斷畫面是否符合描述(``locate_by_description`` 的
  ``verify()`` 搭檔)。``AC_assert_vlm``。
* **捲動找元素** — ``scroll_until_visible(target, kind="image",
  direction="down", max_scrolls=10)`` 往某方向捲動直到樣板圖或 OCR 文字
  出現,回傳 ``{found, coords, scrolls}``。``AC_scroll_to_find``。
* **區域顏色統計** — ``region_color_stats(source, region)`` 回傳區域的
  ``average_rgb``、``dominant_rgb`` 及該色的像素占比(量化色彩空間 → 取
  最多的 bucket → 平均其真實像素)。``AC_region_color_stats``。
* **讀取 QR code** — ``read_qr_codes(source, region)`` 以 OpenCV 的
  ``QRCodeDetector`` 解碼 QR(不需新相依)。``AC_read_qr``。


流程控制與變數
==============

* **可重用巨集** — ``AC_define_macro`` 註冊具名、帶參數的動作子程序;
  ``AC_call_macro`` 以 ``${arg}`` 綁定呼叫它——補上 loop / if 原語表達
  不了的「可呼叫函式」。
* **同進程平行** — ``AC_parallel`` 讓多個分支動作清單並行執行,各自在
  獨立的全新 executor 上,因此分支不會在共享變數上互相 race(跨主機 DAG
  的同進程版)。
* **效能預算斷言** — ``assert_duration(action, max_ms)`` /
  ``AC_assert_duration`` 在區塊耗時超過預算時判失敗——銜接 profiler 與
  斷言 DSL 的延遲回歸守門。
* **讀進變數** — 把外部資料綁進流程範圍供後續 ``${var}`` 使用:
  ``AC_ocr_to_var``(區域文字)、``AC_shell_to_var``(命令 stdout)、
  ``AC_read_file_to_var``(檔案文字)、``AC_http_to_var``(GET body 或
  dotted JSON path)、``AC_now_to_var``(strftime)、``AC_random_to_var``
  (seeded int / float / choice)。
* **變數轉換** — ``AC_transform_var`` 套用 upper / lower / strip / title /
  replace / regex 取出 / slice,可就地或寫入新變數——與「讀進變數」系列
  搭配,在使用前清理原始文字。
* **斷言變數** — ``assert_variable(value, op, expected)`` /
  ``AC_assert_var`` 在變數不滿足 eq / ne / lt / gt / contains / regex 時
  判失敗(分支 ``if_var`` 的斷言 DSL 搭檔)。


觸發器與智慧等待
================

* **複合觸發器** — ``AllOfTrigger`` / ``AnyOfTrigger`` / ``SequenceTrigger``
  以布林 AND、OR 或有序序列組合任何現有觸發器;子項重用各觸發器的
  ``is_fired()``,因此任何型別都能自由巢狀。
* **Cron 觸發器** — ``CronTrigger("0 9 * * *")`` 以五欄 cron 運算式觸發,
  每個符合的分鐘最多一次,並可與布林觸發器組合(例如 *在 09:00 且只在
  圖片可見時*)。
* **更多智慧等待** — ``wait_until_clipboard_changes``(changed / equals /
  contains,``AC_wait_clipboard_change``)與 ``wait_until_window_closed``
  (``AC_wait_window_closed``)補齊 screen / pixel / region 等待。


視窗管理
========

* **單一視窗擷取** — ``capture_window(title, output_path)`` 以標題解析視窗
  geometry(Win32 ``GetWindowRect``)並精確擷取其範圍。``AC_capture_window``。
* **版面儲存 / 還原** — ``save_window_layout(path)`` 把每個視窗的位置快照
  成 JSON;``restore_window_layout(path)`` 再把它們全部移回(方便測試
  setup / teardown)。``AC_save_window_layout`` / ``AC_restore_window_layout``。
* **貼齊 / 平鋪** — ``snap_window(title, "left")`` 把視窗移到螢幕一半
  (left / right / top / bottom)、四分之一(四個角)或 ``"max"``。
  ``AC_snap_window``。


檔案安全
========

* **動作檔簽章** — ``sign_action_file`` 寫出 HMAC-SHA256 的 ``.sig``
  sidecar;``verify_action_file`` 以常數時間驗證。設定
  ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` 時,``execute_files`` 會強制
  簽章(opt-in)。``AC_sign_action_file`` / ``AC_verify_action_file``。
* **動作檔加密** — ``encrypt_action_file`` / ``decrypt_action_file`` 以
  Fernet(AES-128-CBC + HMAC)讓腳本內容在靜態時保密,金鑰來自通行碼或
  每位使用者的 0600 金鑰。``AC_encrypt_action_file`` /
  ``AC_decrypt_action_file``。
* **可還原刪除** — ``move_to_trash(path)`` 把檔案送進 OS 資源回收桶
  (Win32 ``SHFileOperation`` undo flag / macOS Trash / Linux XDG trash,
  優先使用 ``send2trash``),讓「刪除」的檔案能還原。``AC_move_to_trash``。


報告與通知
==========

* **截圖標註** — ``annotate_screenshot(source, annotations, output_path)``
  在截圖上畫出帶標籤的方框、半透明高亮、箭頭與文字(redaction 模糊化的
  標記版搭檔)。``AC_annotate_screenshot``。
* **桌面通知** — ``notify(title, message)`` 顯示跨平台通知
  (``notify-send`` / ``osascript`` / PowerShell);防注入(Linux 用 argv,
  macOS / Windows 用從環境變數讀字串的固定腳本)。``AC_notify``。


GUI
===

* **錄製編輯器 Undo** — 每次編輯(刪步驟、trim、rescale、調整延遲、
  filter)都會快照進 undo stack;**Ctrl+Z** 與 Undo 按鈕可還原前一狀態。
* **觸發器分頁** — *Combine selected* 把選取的觸發器包成 AllOf / AnyOf /
  Sequence 複合觸發器;新增 **Cron** 觸發器型別。
* **斷言分頁** — 新增 **VLM**(「畫面符合描述」)斷言型別。
* 每個新的 ``AC_*`` 指令都可在視覺化 **Script Builder** 中建構。
