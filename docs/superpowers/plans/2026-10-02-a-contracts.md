# A：既有決策與執行契約 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** 完成已核准的 Progress 修正，建立之後改版不能破壞的執行邊界。

**Architecture:** 依核准設計做獨立可測的增量交付，沿用 headless → executor → GUI/MCP 邊界。先確認 Jeffrey_RPA 的 batch/bot 狀態；其使用中的輸入／擷取修改在隔離 checkout 進行。

**Tech Stack:** Python 3.10+、pytest、setuptools、cryptography、既有 executor

**Spec:** [核准設計](../specs/2026-10-02-platform-gui-modernization-design.md)

## Global Constraints

- Python ≥3.10；新檔 ≤750 行；公開 API 有 docstring 與型別；例外屬 AutoControlException。
- 保留 import、AC_* 名稱與舊 CLI 旗標；headless import 不載入 Qt；相依延遲匯入。
- 一般 GUI 面板操作經 Actions menu；重寫模組不得擴大 mypy 豁免或全域忽略。
- `architecture.md`、`architecture_explore.md`、三語 README、對應 Sphinx 文件與 `docs/updates/` 隨交付更新；僅完成的 Progress 條目才刪除。
- 測試使用受控輸入、不操作使用者桌面；有實機證據才標示實機已驗證。

## Review Focus

- 外掛自動載入不能 import je_auto_control 或 Qt。
- 前一次執行的變數不能流入不同呼叫者。
- 逾時回覆不能完成新的 USB 請求。
- 讀取檔案、參照與下載目的地必須服從同一邊界。
- 新版錯誤回報與簽章不能破壞既有 CLI/import 名稱。

## 驗證與提交規則

每個 task 先加重現測試、確認失敗、實作、確認成功、更新相關文件並逐檔提交。
下列 assertion snippets 的測試資料與 fake fixtures 在同一測試模組定義，不能修改 assertion 迎合實作。
Step 4 通過後，該階段另外執行 ruff、相關既有回歸與三目標型別 gate；全面 coverage 與平台 smoke 於整合階段執行。
檔案列出的既有目錄是要逐項檢查的入口；新增模組名稱與以下接口固定，搬移時保留兼容路徑。

---

### Task A1: 精簡 pytest 進入點

**Files:** 修改：`je_auto_control/utils/pytest_plugin/plugin.py`、`pyproject.toml`、`test/unit_test/headless/test_coverage_measurement.py`；新增：`je_auto_control_pytest.py`；測試：`test/unit_test/headless/test_pytest_entrypoint_light.py`。

**Interfaces:** 產出 `je_auto_control_pytest.py` 的既有 fixtures 與 hooks；舊 plugin re-export 相同函式。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_entrypoint_import_is_light, test_legacy_plugin_exports_same_hooks`，驗證：

```python
assert 'je_auto_control' not in imported_modules
assert legacy.pytest_configure is standalone.pytest_configure
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_pytest_entrypoint_light.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 搬移現有輕量 plugin，setuptools 的 py-modules 同時打包頂層模組，pytest11 改指該模組；fixture 內保留延遲 import。更新 coverage 測試前提，保留 coverage run。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A1: 精簡 pytest 進入點'`。

### Task A2: 舊 CLI 的失敗結束碼

**Files:** 修改：`je_auto_control/__main__.py`、`test/unit_test/headless/test_cli_audit_fixes.py`；測試：`test/unit_test/headless/test_legacy_cli_failure_exit.py`。

**Interfaces:** 保留 `-e/--execute_file`、`-d/--execute_dir`、`--execute_str`；命令開始 reset failure count，執行後檢查 recorded_failures。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_execute_str_failure_exit_one, test_legacy_file_and_directory_failure_exit_one`，驗證：

```python
assert failed.returncode == 1
assert succeeded.returncode == 0
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_legacy_cli_failure_exit.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 以不驅動桌面的失敗 command 做 subprocess 重現；頂層只 reset 一次，目錄執行累積所有檔案失敗，維持原有 argparse 錯誤。核對 PyBreeze/TestPioneer 使用端。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A2: 舊 CLI 的失敗結束碼'`。

### Task A3: 獨立執行變數範圍

**Files:** 修改：`je_auto_control/utils/executor/action_executor.py`、`je_auto_control/utils/executor/flow_control.py`、`je_auto_control/utils/script_vars/scope.py`、`je_auto_control/utils/rest_api/rest_handlers.py`、`je_auto_control/utils/mcp_server/tools/_handlers.py`；測試：`test/unit_test/headless/test_execution_scope_isolation.py`。

**Interfaces:** 新增 `execution_scope(variables: Mapping[str, object] | None = None) -> ContextManager[VariableScope]`；各伺服器入口、execute_action_with_vars 與巢狀 adapter 使用一致的 context。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_top_level_vars_do_not_leak, test_parallel_nested_helpers_use_branch_scope`，驗證：

```python
assert second_run_unknown_variable is True
assert sorted(branch_results) == ['left', 'right']
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_execution_scope_isolation.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 先記錄現有 scope 生命周期；頂層建立 scope，巢狀使用當前 scope，parallel branch fork。用 contextvars 或等價 thread-safe context，finally 還原；circuit/bulkhead/chaos/DAG adapter 不再硬取全域 scope。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A3: 獨立執行變數範圍'`。

### Task A4: USB 回覆的請求身分

**Files:** 修改：`je_auto_control/utils/usb/passthrough/protocol.py`、`je_auto_control/utils/usb/passthrough/session.py`、`je_auto_control/utils/usb/passthrough/viewer_client.py`；測試：`test/unit_test/headless/test_usb_request_correlation.py`。

**Interfaces:** JSON request/reply 增加可選 `request_id: str`，client pending 依 request_id 配對；新 host 原樣 echo。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_late_open_does_not_complete_next_open, test_late_transfer_does_not_complete_next_transfer, test_legacy_timeout_requires_reconnect`，驗證：

```python
assert new_request.completed is False
assert next_result == expected_new_reply
assert legacy_claim.reusable is False
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_usb_request_correlation.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 新 peer 的 tombstone pending ID 僅丟棄已過期回覆。舊 peer 在無法判別逾時回覆時將 claim/session 標成不可重用並重連，不使用『丟掉下一則』策略。fragment/error/credit 的配對一併驗證。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A4: USB 回覆的請求身分'`。

### Task A5: 公私鑰簽章與執行權限分離

**Files:** 修改：`je_auto_control/utils/action_signing/signer.py`、`je_auto_control/utils/action_signing/_key_file.py`、`je_auto_control/utils/executor/action_executor.py`；測試：`test/unit_test/headless/test_signing_execution_roles.py`。

**Interfaces:** 新增 version-2 Ed25519 signature envelope 與 `create_signing_keypair(private_path: Path, public_path: Path) -> None`；verify 只需 public key。角色授權另由 A10 交付。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_verifier_has_no_private_key, test_execution_endpoint_cannot_sign, test_legacy_signature_requires_explicit_migration`，驗證：

```python
assert verifier.private_key_path is None
assert execution_endpoint_sign_denied is True
assert implicit_legacy_signature_accepted is False
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_signing_execution_roles.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 明確配置 signer/private key 與 verifier/public key；執行端不能靠預設個人 key 簽章。舊 HMAC envelope 提供明確遷移模式，使用新簽章時 verifier 不讀 private key。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A5: 公私鑰簽章與執行權限分離'`。

### Task A6: MCP 路徑與 viewer 收檔

**Files:** 修改：`je_auto_control/utils/mcp_server/tools/_factories.py`、`je_auto_control/utils/mcp_server/server.py`、`je_auto_control/utils/secret_ref/secret_ref.py`、`je_auto_control/utils/remote_desktop/file_transfer.py`、`je_auto_control/utils/remote_desktop/viewer.py`、`je_auto_control/gui/remote_desktop/viewer_panel.py`；新增：`je_auto_control/utils/path_guard/policy.py`；測試：`test/unit_test/headless/test_file_boundary_policy.py`。

**Interfaces:** `FileReceiver(base_dir: Path | None = None)` 保留 host 用法；viewer 預設使用下載 root。`PathPolicy.validate(path: str, *, operation: str) -> Path` 採 realpath 與語意 metadata。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_semantic_path_fields_only, test_symlink_escape_is_rejected, test_viewer_file_stays_in_download_root, test_env_ref_allowlist`，驗證：

```python
assert json_query_path_is_untouched is True
assert escaped_file_rejected is True
assert received_path.is_relative_to(download_root)
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_file_boundary_policy.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 新增 focused policy 模組；按 schema 語意標記真正檔案欄位。配置 roots 與 roots/list 使用同一策略，未配置不預設唯讀。file/env ref 使用明確 policy，reject symlink、absolute viewer dest、drive/UNC escape；更新舊絕對路徑範例。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A6: MCP 路徑與 viewer 收檔'`。

### Task A7: 發布名稱與專案網址

**Files:** 修改：`je_auto_control/utils/mcp_registry/registry.py`、`pyproject.toml`、`dev.toml`、`README.md`、`README/README_zh-TW.md`、`README/README_zh-CN.md`；測試：`test/unit_test/headless/test_modernization_metadata.py`。

**Interfaces:** 沿用套件名與所有公開 import；新 URL 使用 Integration-Automation/AutoControlGUI；安全相依由 A11 處理。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_registry_uses_approved_name, test_project_urls_use_current_repository`，驗證：

```python
assert server_name == 'io.github.integration-automation/autocontrol'
assert repo_slug == 'Integration-Automation/AutoControlGUI'
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_modernization_metadata.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 改所有現行 URL 與 registry payload；驗證 wheel/sdist metadata 與三語 README 對帳，保留發布套件名稱。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A7: 發布名稱與專案網址'`。

### Task A8: 多螢幕與 DPI 座標契約

**Files:** 修改：`je_auto_control/windows/screen/win32_screen.py`、`je_auto_control/utils/monitor_layout/logical_frame.py`、`je_auto_control/utils/cv2_utils/screenshot.py`、`je_auto_control/utils/window_capture/window_capture.py`、`je_auto_control/utils/set_of_marks/set_of_marks.py`、`je_auto_control/gui/_screen_geometry.py`；測試：`test/unit_test/headless/test_platform_coordinate_contract.py`。

**Interfaces:** 沿用 wrapper 簽章；所有定位回傳 backend 接受的 logical/global point。Windows 啟用 per-monitor v2，macOS 每螢幕縮放並拼接。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_negative_secondary_monitor_capture, test_retina_maps_to_points, test_marks_include_virtual_origin`，驗證：

```python
assert logical_click == (100, 50)
assert captured_secondary_is_black is False
assert marked_points == expected_global_points
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_platform_coordinate_contract.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 修 per-monitor v2、Windows 區域／視窗擷取與 set-of-marks 原點，macOS 逐螢幕 point 座標擷取、縮放、拼接。使用相同 logical/global 契約；下游兩支 GUI 契約測試必跑。實機 Retina 與混合 DPI 結果附測試條件。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A8: 多螢幕與 DPI 座標契約'`。

### Task A9: Agent 歷史與真實 API 驗證

**Files:** 修改：`je_auto_control/utils/agent/backends/base.py`、`je_auto_control/utils/agent/backends/anthropic.py`、`je_auto_control/utils/agent/backends/anthropic_computer_use.py`；測試：`test/unit_test/headless/test_agent_append_only_history.py`。

**Interfaces:** 新增 `compact_history(messages: Sequence[object], summary: str, latest_screenshot: object) -> list[object]` 的 provider adapter；維持 AC_run_agent 的既有工具集。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_sent_turns_are_never_mutated, test_compaction_opens_new_history, test_default_agent_tools_are_unchanged`，驗證：

```python
assert sent_turns == original_sent_turns
assert compacted_history[0].contains_goal_and_actions
assert default_tools == original_tools
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_agent_append_only_history.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 超過截圖上限時建立目標／已執行動作摘要與最新截圖的新對話，不改已送訊息。按照當前官方 API 驗證兩條 Anthropic 路徑。paid smoke 僅在配置可用時執行；預設 toolset 切換仍需真實 API 結果。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A9: Agent 歷史與真實 API 驗證'`。

### Task A10: REST/MCP 角色授權

**Files:** 修改：`je_auto_control/utils/rbac/users.py`、`je_auto_control/utils/rest_api/rest_auth.py`、`je_auto_control/utils/mcp_server/http_transport.py`、`je_auto_control/utils/mcp_server/audit.py`、`je_auto_control/gui/admin_console_tab.py`；測試：`test/unit_test/headless/test_rbac_server_wiring.py`。

**Interfaces:** `AuthorizationContext(user_id: str, role: str)`；REST/MCP 在 bearer 驗證後使用既有 `UserStore.authenticate`、`can(role, capability)`。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_viewer_cannot_execute, test_operator_cannot_sign, test_unconfigured_rbac_keeps_shared_token, test_user_id_in_audit`，驗證：

```python
assert viewer_execute_denied is True
assert legacy_token_accepted is True
assert audit_entry['user_id'] == authenticated_user
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_rbac_server_wiring.py`，確認新測試因原有缺陷 FAIL。
- [ ] **Step 3:** RBAC opt-in，未配置沿用既有 shared token。路由與 tool 依 capability 授權，搜尋與執行一致，audit 攜帶 user_id；admin GUI 連到同一 UserStore，不能用單一 token 驗證成功就授予全部角色。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0，再執行相關既有回歸與型別 gate。
- [ ] **Step 5:** 更新對應交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A10: REST/MCP 角色授權'`。

### Task A11: 安全相依下限與安裝矩陣

**Files:** 修改：`pyproject.toml`、`uv.lock`、`test/unit_test/headless/test_arm64_dependency_markers.py`、`docs/CAPABILITY_MATRIX.md`；測試：`test/unit_test/headless/test_crypto_fifty_install_contract.py`。

**Interfaces:** cryptography floor `>=50.0.0`，保留平台 optional markers；公開的 crypto 操作失敗有型別與安裝說明。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_crypto_floor_is_fifty, test_arm64_import_has_no_crypto_requirement, test_missing_crypto_feature_is_typed`，驗證：

```python
assert crypto_minimum >= (50, 0, 0)
assert facade_import_without_crypto_succeeds is True
assert error.has_install_instruction
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_crypto_fifty_install_contract.py`，確認新測試因原有缺陷 FAIL。
- [ ] **Step 3:** 重產 lock、查核當前安全與官方 wheel metadata，Windows arm64 與 Intel Mac binary probe 分開留結果。缺依賴時只停受影響能力；簽章使用安全算法，不以舊 wheel 降低下限。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0，再執行相關既有回歸與型別 gate。
- [ ] **Step 5:** 更新對應交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A11: 安全相依下限與安裝矩陣'`。

### Task A12: 視窗管理與擷取位置

**Files:** 修改：`je_auto_control/wrapper/window_backends/macos_backend.py`、`je_auto_control/windows/window/windows_window_manage.py`、`je_auto_control/utils/window_capture/window_capture.py`、`je_auto_control/wrapper/auto_control_window.py`、`je_auto_control/utils/window_zorder/window_zorder.py`；測試：`test/unit_test/headless/test_window_lifecycle_contract.py`。

**Interfaces:** 沿用 `restore(window_id)`、`capture_window(...)`、`wait_for_window(...)`；_info_for 查詢包括最小化 window；focus 以真實 foreground 狀態驗證。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_restore_minimized_macos_window, test_capture_does_not_move_window, test_foreground_failure_propagates, test_cloaked_window_filtered, test_poll_is_bounded`，驗證：

```python
assert restored_window.visible is True
assert placement_after == placement_before
assert poll_sleep <= remaining_timeout
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_window_lifecycle_contract.py`，確認新測試因原有缺陷 FAIL。
- [ ] **Step 3:** CGWindow including-window 查詢；Windows focus/zorder 回傳真實失敗、過濾 DWM cloak、Get/SetWindowPlacement 還原原位；布局使用 work area，poll 用 clamp。post_key 對一般文字與控制鍵各自只送正確事件，避免重複文字。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0，再執行相關既有回歸與型別 gate。
- [ ] **Step 5:** 更新對應交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A12: 視窗管理與擷取位置'`。

### Task A13: 鍵鼠輸入、秘密與 Unicode

**Files:** 修改：`je_auto_control/wrapper/auto_control_keyboard.py`、`je_auto_control/wrapper/auto_control_mouse.py`、`je_auto_control/utils/text_unicode/text_unicode.py`、`je_auto_control/utils/keyboard_layout/keyboard_layout.py`、`je_auto_control/utils/clipboard_formats/clipboard_formats.py`、`je_auto_control/utils/executor/action_executor.py`；測試：`test/unit_test/headless/test_input_wrapper_contract.py`。

**Interfaces:** `write(..., secret: bool = False)`、新增 `write_secret(...)` 與 `AC_write_secret` 相容別名；既有參數名不改，Shift 以 finally 釋放；座標使用 `int(round(value))`。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_case_and_shift_preserved, test_crlf_sends_single_enter, test_nan_does_not_move_mouse, test_scroll_direction_and_rounding, test_write_secret_leaves_no_text, test_dead_key_and_oem_layout`，驗證：

```python
assert enter_events_for_crlf == 1
assert mouse_events_for_nan == []
assert secret not in logs_and_records
assert dead_key_shift_value is None
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_input_wrapper_contract.py`，確認新測試因原有缺陷 FAIL。
- [ ] **Step 3:** 依 Progress 的逐項重現修 case/shift/CRLF/scroll/NaN/OEM、Unicode控制鍵與clipboard None名。私有 WinDLL 避免 prototype 汙染。secret 在 logger/record/callback/return 邊界都不含原文，WebRunner WR_ac_basic_auth 契約測試一起更新。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0，再執行相關既有回歸與型別 gate。
- [ ] **Step 5:** 更新對應交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A13: 鍵鼠輸入、秘密與 Unicode'`。

### Task A14: 影像讀取、OCR 與區域邊界

**Files:** 修改：`je_auto_control/utils/cv2_utils/template_detection.py`、`je_auto_control/utils/cv2_utils/image_file.py`、`je_auto_control/utils/ocr/text_span.py`、`je_auto_control/wrapper/auto_control_image.py`、`je_auto_control/utils/monitor_layout/logical_frame.py`；測試：`test/unit_test/headless/test_image_ocr_coordinate_contract.py`。

**Interfaces:** 沿用 image/OCR 公開入口；模板讀取經 `read_image`；center 使用整數 `// 2`；region與虛擬桌面先做交集驗證。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_unicode_template_path, test_grayscale_template, test_partial_ocr_left_span_preserved, test_negative_center_floor, test_empty_region_rejected`，驗證：

```python
assert found_from_unicode_path is True
assert partial_phrase_found is True
assert negative_center == (-2, -2)
assert invalid_region_rejected_before_capture is True
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_image_ocr_coordinate_contract.py`，確認新測試因原有缺陷 FAIL。
- [ ] **Step 3:** 支援Unicode路徑與2-D模板，typed miss錯誤。OCR丟左框只在剩餘字數仍足以包含目標時；空／負區域先拒絕。測負座標及跨螢幕region與 A8 契約一致，下游GUI契約驗證後交付。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0，再執行相關既有回歸與型別 gate。
- [ ] **Step 5:** 更新對應交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'A14: 影像讀取、OCR 與區域邊界'`。
