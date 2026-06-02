==================================
新功能 (2026-06) — 測試框架層
==================================

新增 9 個功能，把 AutoControl 的自動化原語升級成一套完整的**測試框架**：
驗證畫面狀態、用資料驅動腳本、偵測並隔離不穩定測試、執行計分套件、輸出 CI
原生報告、稽核無障礙 / i18n、跨裝置矩陣並行執行，以及對音訊 / 影片做斷言。
每個功能都遵循框架既有模式：headless Python API、``AC_*`` executor 命令、
``ac_*`` MCP 工具，以及 Qt GUI 分頁。

.. contents::
   :local:
   :depth: 2


斷言
====

斷言 DSL
--------

驗證畫面狀態，而不只是操作畫面。每個 ``assert_*`` 觀察當前狀態、回傳
:class:`AssertionResult`，並（預設）在不符時拋出
``AutoControlAssertionException``，讓腳本 / 測試 / 排程在錯誤假設處明確失敗::

    from je_auto_control import (
        assert_text, assert_image, assert_pixel, assert_window,
    )

    assert_text("Login successful", region=[0, 0, 800, 200])
    assert_image("checkmark.png", threshold=0.9)
    assert_pixel(100, 200, [0, 200, 0], tolerance=10)
    assert_window("Settings", exists=True)

``assert_text`` 支援 ``regex=True`` 與 ``present=False``（斷言「不存在」）；
每個函式都接受 ``raise_on_fail`` 與 ``capture_on_fail``（將失敗畫面截圖存到
``~/.je_auto_control/assertions/``）。

Executor：``AC_assert_text / _image / _pixel / _window``。
MCP：``ac_assert_*``。GUI：**Assertions** 分頁。


媒體斷言（音訊 / 影片）
----------------------

斷言某個東西確實「播放」或「動」了::

    from je_auto_control import assert_audio_activity, assert_video_changes

    assert_audio_activity(duration_s=1.0, threshold=0.01, expect_sound=True)
    assert_video_changes("clip.mp4", start_s=0, end_s=3, expect_motion=True)

``assert_audio_activity`` 從輸入裝置錄音並比較 RMS 音量與門檻（有聲 vs 靜音）。
``assert_video_changes`` 量測影片區段的相鄰影格平均差異（動態 vs 靜止），可選
``region`` 裁切。數值核心（``rms``、``mean_frame_diff``、``measure_audio_rms``、
``video_segment_motion``）為公開純函式。``sounddevice`` / OpenCV 為延遲載入依賴。

Executor：``AC_assert_audio / AC_assert_video_changes``。
MCP：``ac_assert_audio / ac_assert_video_changes``。GUI：**Media Checks** 分頁。


資料驅動執行
============

將 CSV / JSON / SQLite / Excel / 內嵌字面值的列資料餵進 ``${var}`` 腳本，
然後每列執行同一段 body::

    from je_auto_control import load_rows

    rows = load_rows({"kind": "csv", "path": "users.csv"})

在 JSON action 檔中，新的 ``AC_for_each_row`` 區塊命令會載入資料來源，
並把每列綁定到一個變數，其欄位可用 ``${row.column}`` 取用::

    ["AC_for_each_row", {
        "source": {"kind": "csv", "path": "users.csv"},
        "as": "row",
        "body": [
            ["AC_type_keyboard", {"keys": "${row.username}"}],
            ["AC_assert_text", {"text": "${row.expected}"}]
        ]
    }]

SQLite 連接器**只允許單句唯讀** ``SELECT`` / ``WITH``（多語句 / 寫入查詢一律拒絕）；
所有檔案路徑皆經 ``realpath`` 驗證。``${var}`` 插值現在能解析點號路徑進 dict 鍵
與 list 索引（``${row.user}``、``${results.0}``），並保留值的型別。

Executor：``AC_load_data`` + ``AC_for_each_row``。
MCP：``ac_load_data``。GUI：**Data Sources** 分頁。


不穩定測試偵測與隔離
====================

不穩定報告
----------

從 SQLite 執行歷史評分間歇性失敗。執行記錄依 ``script_path``（或 ``source_id``）
分組；報告統計通過 / 失敗次數，以及依時間順序的通過↔失敗*翻轉*次數，
讓不穩定腳本排在持續綠燈或持續紅燈的腳本之上::

    from je_auto_control import analyze_flakiness

    report = analyze_flakiness(min_runs=3)
    for entry in report.entries:
        print(entry.key, entry.flip_rate, entry.flaky)

Executor：``AC_flaky_report``。MCP：``ac_flaky_report``。
GUI：**Flaky Tests** 分頁。


隔離（閉環處理）
----------------

被隔離的案例名稱會被套件執行器*跳過*（記為 ``skipped``，原因 ``quarantined``），
讓已知不穩定的案例在修好前不再污染套件的紅 / 綠狀態。隔離區是一個小型 JSON
檔（POSIX 上為 0600 權限），可跨重啟保存::

    from je_auto_control import (
        default_quarantine_store, auto_quarantine_from_flakiness,
    )

    default_quarantine_store().add("login_suite", reason="under triage")
    auto_quarantine_from_flakiness(flip_rate_threshold=0.5)

``auto_quarantine_from_flakiness`` 讀取不穩定報告，並隔離所有超過翻轉率門檻的群組。

Executor：``AC_quarantine_add / _remove / _list / _clear / _auto``。
MCP：``ac_quarantine_*``。GUI：**Test Suites** 分頁上的隔離區面板。


QA 套件執行器 + CI 報告
=======================

套件編排
--------

把扁平的 action list 變成具備 setup / teardown、標籤與逐案例通過 / 失敗計分的
測試案例。帶有 ``data`` 來源的案例會展開成每列一個計分案例::

    from je_auto_control import run_suite

    spec = {
        "name": "Login",
        "setup":    [["AC_focus_window", {"title": "MyApp"}]],
        "teardown": [["AC_close_window", {"title": "MyApp"}]],
        "cases": [
            {"name": "valid login", "tags": ["smoke"],
             "actions": [["AC_assert_text", {"text": "Welcome"}]]},
            {"name": "each user", "as": "row",
             "data": {"kind": "csv", "path": "users.csv"},
             "actions": [["AC_assert_text", {"text": "${row.expected}"}]]},
        ],
    }
    result = run_suite(spec, tags=["smoke"])
    print(result.passed, result.failed, result.errored, result.skipped)

``AutoControlAssertionException`` 將案例標為**失敗**；其他例外標為**錯誤**；
乾淨執行為**通過**；被隔離的案例名稱記為**跳過**。

Executor：``AC_run_suite``。MCP：``ac_run_suite``。GUI：**Test Suites** 分頁。


CI 原生報告（JUnit / Allure）
-----------------------------

輸出 Jenkins、GitHub Actions、GitLab CI 與 Allure 能原生解析的報告::

    from je_auto_control import write_junit_xml, write_allure_results

    write_junit_xml(result, "reports/junit.xml")
    write_allure_results(result, "reports/allure")

``AC_run_suite`` 在傳入 ``junit_path`` / ``allure_dir`` 時會直接一併寫出::

    ["AC_run_suite", {"spec": {...}, "junit_path": "reports/junit.xml"}]

此處只負責報告*產生*（絕不解析不可信 XML），因此使用標準庫
``xml.etree.ElementTree`` 寫出是安全的。


無障礙 & i18n 稽核
==================

反向利用無障礙樹與 OCR 層，去*檢查*介面常見的無障礙 / 在地化缺陷，
而非用來操作::

    from je_auto_control import run_audit, contrast_ratio

    report = run_audit(
        app_name="MyApp",
        contrast_pairs=[{"foreground": [120, 120, 120],
                         "background": [255, 255, 255], "label": "hint"}],
        texts=["Save chang…"],   # 用來掃描截斷的 OCR 字串
    )

檢查項目：

* **缺漏標籤** — 無障礙樹中沒有可存取名稱的互動元件（按鈕、選單項、連結、
  輸入框…）。
* **對比度** — WCAG 2.x 相對亮度對比率，含 AA / AAA 門檻
  （``contrast_ratio([0,0,0],[255,255,255]) == 21.0``）。
* **截斷** — 以省略號結尾的 OCR 字串（翻譯後被切掉）。

Executor：``AC_audit_accessibility / AC_audit_contrast``。
MCP：``ac_audit_*``。GUI：**A11y Audit** 分頁。


行動裝置矩陣
============

將單一 action list **並行**分發到多台 Android / iOS 裝置，每台使用各自獨立的
executor（執行緒間的執行期變數作用域互不衝突）。腳本透過綁定的 ``${device.*}``
變數鎖定當前裝置::

    from je_auto_control import run_on_devices

    report = run_on_devices(
        actions=[["AC_android_tap", {"x": 100, "y": 200,
                                     "serial": "${device.serial}"}]],
        devices=[{"platform": "android", "serial": "emulator-5554"},
                 {"platform": "android", "serial": "emulator-5556"}],
        max_parallel=4,
    )
    print(report.passed, report.failed)

單台裝置的失敗會被隔離——絕不中斷其他裝置。

Executor：``AC_run_device_matrix``。MCP：``ac_run_device_matrix``。
GUI：**Device Matrix** 分頁。
