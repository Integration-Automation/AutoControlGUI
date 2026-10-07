# D：Wayland 與原生依賴可靠性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** 修正 Wayland 生命周期，提供可測替代後端及正確的能力診斷。

**Architecture:** 依核准設計做獨立可測的增量交付，沿用 headless → executor → GUI/MCP 邊界。依賴 A 座標、B 日誌、C session；不修改使用者桌面環境或自動取得裝置權限。

**Tech Stack:** D-Bus portal、libei/liboeffis、helper process、stdlib IPC、既有 Docker jobs

**Spec:** [核准設計](../specs/2026-10-02-platform-gui-modernization-design.md)

## Global Constraints

- Python ≥3.10；新檔 ≤750 行；公開 API 有 docstring 與型別；例外屬 AutoControlException。
- 保留 import、AC_* 名稱與舊 CLI 旗標；headless import 不載入 Qt；相依延遲匯入。
- 一般 GUI 面板操作經 Actions menu；重寫模組不得擴大 mypy 豁免或全域忽略。
- `architecture.md`、`architecture_explore.md`、三語 README、對應 Sphinx 文件與 `docs/updates/` 隨交付更新；僅完成的 Progress 條目才刪除。
- 測試使用受控輸入、不操作使用者桌面；有實機證據才標示實機已驗證。

## Review Focus

- 拒絕 portal 授權必須立即停止請求。
- 半開交握不能 crash GUI 或無限漏 fd。
- 裝置暫停／移除後不能繼續送輸入。
- 錄製不能把本身注入的輸入再錄一次。
- native CI segfault 必須產生可定位的 crash artifact。

## 驗證與提交規則

每個 task 先加重現測試、確認失敗、實作、確認成功、更新相關文件並逐檔提交。
下列 assertion snippets 的測試資料與 fake fixtures 在同一測試模組定義，不能修改 assertion 迎合實作。
Step 4 通過後，該階段另外執行 ruff、相關既有回歸與三目標型別 gate；全面 coverage 與平台 smoke 於整合階段執行。
檔案列出的既有目錄是要逐項檢查的入口；新增模組名稱與以下接口固定，搬移時保留兼容路徑。

---

### Task D1: 能力與授權狀態機

**Files:** 修改：`je_auto_control/linux_wayland/portal.py`、`je_auto_control/linux_wayland/_select_input.py`、`je_auto_control/linux_wayland/capture.py`、`je_auto_control/gui/diagnostics_tab.py`；新增：`je_auto_control/wrapper/capabilities.py`；測試：`test/unit_test/headless/test_wayland_capability_states.py`。

**Interfaces:** `CapabilityStatus` 與 `probe_capabilities(context: BackendContext) -> CapabilitySnapshot`；探測沒有控制或授權副作用。

- [x] **Step 1:** 定義 fake fixtures 並新增 `test_cancel_does_not_fallback_silently, test_revoked_session_cannot_send, test_xwayland_scope_is_explicit`，驗證：

```python
assert canceled.state == 'needs_permission'
assert writes_after_revoke == 0
assert xwayland.desktop_wide is False
```

- [x] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_wayland_capability_states.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [x] **Step 3:** 輸入／擷取獨立選擇與診斷，portal request/session close、restore token、compositor 重啟走明確狀態；GUI 顯示可操作修正與停止控制，headless/AC/MCP 使用同一 capability。
- [x] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [x] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'D1: 能力與授權狀態機'`。

D1 實作與本機／替身驗證已交付；原生 GNOME/KDE、EI 與 restore-token 替代接口仍需 D2/D3/H3 證據，不以離線測試代替。

### Task D2: libei crash 隔離與 backend 相依

**Files:** 修改：`je_auto_control/linux_wayland/libei.py`、`docker/libei_verify.py`、`docker/eis_verify.py`、`test/unit_test/headless/test_arm64_dependency_markers.py`；新增：`je_auto_control/linux_wayland/ei_worker.py`、`je_auto_control/linux_wayland/ei_transport.py`；測試：`test/unit_test/headless/test_wayland_worker_cleanup.py`。

**Interfaces:** `EiWorkerClient.send(batch: Sequence[InputEvent], *, timeout_s: float) -> InputAck`、`close() -> None`；有界 batch、request IDs 與 cancellation。

原生驗證 checkpoint：半開連線對 libei `1.3.901-1` 的 `ei_unref` 仍為 SIGSEGV（rc=-11）。
兩支 sentinel 現在要求到達清理前／後的 marker，將 probe 設定錯誤及其他訊號視為失敗，
並有 60 秒上限與 faulthandler 輸出。EIS 映像同時提供半開探針，CI 保留驗證輸出。
本機原生執行結果：libei 9/9、EIS 20/20 檢查成功；完整交握後釋放 device refs 再
`ei_unref` 安全。EIS 未公告 pause，因此 paused-device 與完整序號傳遞不列為實測證據。
這是 D2 的驗證前置交付；不能因此標示 D2 已交付。

Helper 階段已交付：`ei_transport.py`／`ei_worker.py` 接到預設 libei 輸入路徑，
提供有界 JSON、request IDs、整批驗證、總時限、取消與 process/fd 回收。
`docker/ei_worker_verify.py` 在已安裝 wheel 的 Linux/Python 3.12 容器通過 3/3 原生檢查；
三次半開失敗的父程序 fd 為 7→7，正常 EOF 釋放 Shift，SIGABRT 不影響父程序且保留 stack。
50 次 permission IPC 的 p50/p95 為 0.18/0.25 ms（容器測量，非桌面反應時間）。
影像替代階段已交付：OpenCV 缺少時以 NumPy／Pillow 提供有界灰階樣板比對、
BGR 截圖、影像檔、預覽及固定畫面自愈；Windows arm64 的 NumPy 2.4.6 wheel
在 Python 3.11–3.14 解析成功，OpenCV／安全 crypto wheel 仍不可用。
本機 OpenCV 對照及封鎖 OpenCV 的測試完成；Windows arm64 原生 platform smoke
及 crash 後實體桌面鍵態恢復的 GNOME/KDE 證據仍由 D3/H3 驗收。

- [x] **Step 1:** 定義 fake fixtures 並新增 `test_half_open_worker_exit_reclaims_resources, test_worker_death_releases_pressed_keys, test_missing_dependency_is_typed`，驗證：

```python
assert active_workers == 0
assert fd_count_after == fd_count_before
assert error.capability == unavailable_capability
```

- [x] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_wayland_worker_cleanup.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [x] **Step 3:** 先跑現有 real-EI verify 精確分類 unsafe teardown；合法清理仍 crash 才啟用 helper。IPC 上限、超時與退場，測量延遲。arm64 影像能力用 backend seam 提供可行替代並逐項矩陣驗證；crypto 維持安全版本與可選診斷。
- [x] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [x] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'D2: libei crash 隔離與 backend 相依'`。

### Task D3: 錄製、全域停止與原生驗證

**Files:** 修改：`je_auto_control/linux_wayland/listener.py`、`je_auto_control/linux_wayland/record.py`、`docker`、`test/unit_test/headless/test_usb_acl_prompt.py`、`.github/workflows`；新增：`je_auto_control/linux_wayland/input_events.py`、`je_auto_control/linux_wayland/global_shortcuts.py`；測試：`test/unit_test/headless/test_wayland_recording_paths.py`。

**Interfaces:** `PhysicalRecorder.start(devices: Sequence[InputDevice]) -> None`、`stop() -> list[InputEvent]`；`StopShortcutSession.close() -> None`。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_action_recording_needs_no_global_hook, test_physical_reader_excludes_virtual_device, test_permission_denial_is_actionable, test_shortcut_session_closes`，驗證：

```python
assert injected_events == []
assert executor_journal_steps == expected_steps
assert permission_error.has_recovery_instruction
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_wayland_recording_paths.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 明確 opt-in 的物理 event reader，排除 virtual/uinput source；不將 portal InputCapture 誤用為普通全域 hook。整合現有 WL compositor CI，新增 GNOME/KDE 授權允許／拒絕人工步驟。USB ACL 3.10 用 faulthandler/native backtrace 重現後修 Qt/native lifecycle，保留 crash log artifact。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'D3: 錄製、全域停止與原生驗證'`。
