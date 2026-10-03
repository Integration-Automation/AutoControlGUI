# C：持久化同步與遠端 session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** 讓多機設定在重啟、離線及並行更新後仍一致，並隔離遠端連線所有權。

**Architecture:** 依核准設計做獨立可測的增量交付，沿用 headless → executor → GUI/MCP 邊界。依賴 A context；使用 B 的 journal 記同步操作。

**Tech Stack:** SQLite、stdlib HTTP、FastAPI 既有 signaling、typed envelopes

**Spec:** [核准設計](../specs/2026-10-02-platform-gui-modernization-design.md)

## Global Constraints

- Python ≥3.10；新檔 ≤750 行；公開 API 有 docstring 與型別；例外屬 AutoControlException。
- 保留 import、AC_* 名稱與舊 CLI 旗標；headless import 不載入 Qt；相依延遲匯入。
- 一般 GUI 面板操作經 Actions menu；重寫模組不得擴大 mypy 豁免或全域忽略。
- `architecture.md`、`architecture_explore.md`、三語 README、對應 Sphinx 文件與 `docs/updates/` 隨交付更新；僅完成的 Progress 條目才刪除。
- 測試使用受控輸入、不操作使用者桌面；有實機證據才標示實機已驗證。

## Review Focus

- server 重啟不能丟設定。
- 兩台機器同時 push 不能靜默覆寫。
- 離線裝置不能讓已刪除資料復活。
- 舊面板的 callback 不能切斷新連線。
- 腳本同步不能自動執行或啟用觸發器。

## 驗證與提交規則

每個 task 先加重現測試、確認失敗、實作、確認成功、更新相關文件並逐檔提交。
下列 assertion snippets 的測試資料與 fake fixtures 在同一測試模組定義，不能修改 assertion 迎合實作。
Step 4 通過後，該階段另外執行 ruff、相關既有回歸與三目標型別 gate；全面 coverage 與平台 smoke 於整合階段執行。
檔案列出的既有目錄是要逐項檢查的入口；新增模組名稱與以下接口固定，搬移時保留兼容路徑。

---

### Task 1: C1 持久化與 CAS server

**Files:** 修改：`je_auto_control/utils/remote_desktop/signaling_server.py`；新增：`je_auto_control/utils/config_sync/store.py`；測試：`test/unit_test/headless/test_config_sync_persistence.py`。

**Interfaces:** `ConfigStore.commit(user_id: str, bucket: ConfigBucket, *, base_revision: int, operation_id: str) -> int`；revision 檢查／寫入在一個 SQLite transaction，重複 operation 回原 revision。

- [x] **Step 1:** 定義 fake fixtures 並新增 `test_reopen_preserves_bucket, test_stale_revision_conflicts, test_operation_retry_is_idempotent`，驗證：

```python
assert reopened.get(user).revision == committed_revision
assert stale_response.status_code == 409
assert repeated.revision == original.revision
```

- [x] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_config_sync_persistence.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [x] **Step 3:** version-2 PUT 以 base_revision/operation_id 加 envelope，GET 回 committed revision。設定 store 路徑 lazy resolve，account isolation、body cap 與共享 secret 規則沿用；舊 blind write 需明確相容設定。
- [x] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [x] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'C1: 持久化與 CAS server'`。

### Task 2: C2 因果合併、刪除與離線 outbox

**Files:** 修改：`je_auto_control/utils/config_sync/client.py`、`je_auto_control/utils/config_sync/__init__.py`；新增：`je_auto_control/utils/config_sync/versions.py`、`je_auto_control/utils/config_sync/outbox.py`；測試：`test/unit_test/headless/test_config_sync_convergence.py`。

**Interfaces:** `SyncEntry` 帶 version vector/operation/origin；`merge_entries(left: SyncEntry, right: SyncEntry) -> MergeDecision`；`SyncOutbox.enqueue(operation: SyncOperation) -> None`。

- [x] **Step 1:** 定義 fake fixtures 並新增 `test_parallel_edits_preserve_conflict, test_restart_retries_outbox, test_retired_peer_requires_full_sync, test_clock_skew_does_not_choose_winner`，驗證：

```python
assert conflict.local == left and conflict.remote == right
assert tombstone.is_deleted is True
assert wall_clock_does_not_change_merge is True
```

- [x] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_config_sync_convergence.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [x] **Step 3:** 同 key 並行變更保留 conflict；outbox SQLite 以 operation ID 重送，有限退避與取消。tombstone 依 peer acknowledged revision 回收；退休 peer 明確 full resync。修掉 __init__ 的過期 endpoint 說明。
- [x] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [x] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'C2: 因果合併、刪除與離線 outbox'`。

### Task 3: C3 設定／資產 adapter 與同步 UI

**Files:** 修改：`je_auto_control/utils/remote_desktop/file_sync.py`、`je_auto_control/utils/remote_desktop/clipboard_sync.py`；新增：`je_auto_control/utils/config_sync/adapters.py`、`je_auto_control/utils/config_sync/assets.py`、`je_auto_control/gui/config_sync_tab.py`；測試：`test/unit_test/headless/test_sync_adapters.py`。

**Interfaces:** `SyncAdapter.snapshot() -> Mapping[str, SyncEntry]`、`apply(entries: Mapping[str, SyncEntry]) -> ApplyReport`；`sync_assets(manifest: AssetManifest, transport: AssetTransport) -> AssetSyncResult`。

- [x] **Step 1:** 定義 fake fixtures 並新增 `test_script_asset_hash_round_trip, test_sync_never_enables_trigger, test_secret_is_local, test_clipboard_does_not_echo`，驗證：

```python
assert received_hash == source_hash
assert enabled_triggers == []
assert sync_payload_contains_secret is False
```

- [x] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_sync_adapters.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [x] **Step 3:** 先寫 script/locator/hotkey/trigger/address-book adapters，秘密及機器路徑留下參照。hash 驗證與 atomic replace；同步面板顯示 revision/pending/conflict/offline，取消 worker 釋放；folder/clipboard loop 與斷線場景也回歸。
- [x] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [x] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'C3: 設定／資產 adapter 與同步 UI'`。

### Task 4: C4 遠端 session 擁有權

**Files:** 修改：`je_auto_control/utils/remote_desktop/registry.py`、`je_auto_control/gui/remote_desktop/connection_screen.py`、`je_auto_control/gui/remote_desktop/viewer_panel.py`、`je_auto_control/gui/remote_desktop/webrtc_panel.py`、`je_auto_control/utils/executor/action_executor.py`；新增：`je_auto_control/utils/remote_desktop/sessions.py`；測試：`test/unit_test/headless/test_remote_session_ownership.py`。

**Interfaces:** `RemoteSession` 擁有 id/owner/transport/state；`disconnect_session(session_id: str, *, owner: str | None = None) -> SessionStatus`；既有 AC_remote_* 加 optional session_id。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_panel_disconnect_only_own_session, test_stale_callback_is_ignored, test_default_script_session_is_compatible`，驗證：

```python
assert other_session.connected is True
assert stale_frame_delivered is False
assert default_script_target == script_session.id
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_remote_session_ownership.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** registry 改 map 與 script default alias；每個 GUI 面板持有自己的 session，生命周期事件通知 owner，舊 callback 查 session ID。拆 webrtc_panel 過長責任，與工具 schema、builder 一起更新。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'C4: 遠端 session 擁有權'`。
