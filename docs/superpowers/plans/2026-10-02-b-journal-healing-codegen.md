# B：動作日誌、自愈量測與候選腳本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** 讓動作來源可追溯、自愈版本可比較，並從日誌產生可驗證的候選腳本。

**Architecture:** 依核准設計做獨立可測的增量交付，沿用 headless → executor → GUI/MCP 邊界。依賴 A 的執行 scope、秘密處理與座標契約。

**Tech Stack:** stdlib JSONL、dataclasses、既有 codegen/locator、pytest

**Spec:** [核准設計](../specs/2026-10-02-platform-gui-modernization-design.md)

## Global Constraints

- Python ≥3.10；新檔 ≤750 行；公開 API 有 docstring 與型別；例外屬 AutoControlException。
- 保留 import、AC_* 名稱與舊 CLI 旗標；headless import 不載入 Qt；相依延遲匯入。
- 一般 GUI 面板操作經 Actions menu；重寫模組不得擴大 mypy 豁免或全域忽略。
- `architecture.md`、`architecture_explore.md`、三語 README、對應 Sphinx 文件與 `docs/updates/` 隨交付更新；僅完成的 Progress 條目才刪除。
- 測試使用受控輸入、不操作使用者桌面；有實機證據才標示實機已驗證。

## Review Focus

- 秘密不得先寫入日誌才遮罩。
- 取消或未結束的動作不能看起來已成功。
- 未知標籤不能被計入自愈正確率。
- parallel/loop 日誌不能被誤還原成未執行的流程。
- 產碼不得執行輸入內容。

## 驗證與提交規則

每個 task 先加重現測試、確認失敗、實作、確認成功、更新相關文件並逐檔提交。
下列 assertion snippets 的測試資料與 fake fixtures 在同一測試模組定義，不能修改 assertion 迎合實作。
Step 4 通過後，該階段另外執行 ruff、相關既有回歸與三目標型別 gate；全面 coverage 與平台 smoke 於整合階段執行。
檔案列出的既有目錄是要逐項檢查的入口；新增模組名稱與以下接口固定，搬移時保留兼容路徑。

---

### Task B1: 結構化動作日誌

**Files:** 修改：`je_auto_control/utils/executor/action_executor.py`、`je_auto_control/utils/executor/action_redaction.py`、`je_auto_control/utils/run_history/history_store.py`；新增：`je_auto_control/utils/action_journal/__init__.py`、`je_auto_control/utils/action_journal/events.py`、`je_auto_control/utils/action_journal/store.py`；測試：`test/unit_test/headless/test_action_journal.py`。

**Interfaces:** `ActionEvent` frozen dataclass，schema_version=1；`ActionJournal.append(event: ActionEvent) -> None`；`read_events(path: Path, *, run_id: str | None = None) -> list[ActionEvent]`。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_redaction_precedes_append, test_parallel_parent_and_order, test_incomplete_step_stays_incomplete`，驗證：

```python
assert password not in journal_text
assert all(event.run_id == run_id for event in events)
assert unfinished.status == 'incomplete'
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_action_journal.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 在 executor 動作邊界記錄 typed input/outcome 與 parent ID，先 redaction 再持久化，保留不可重播欄位的原因。沿用 atomic/json-store 邊界；完整 typed public/export/AC/GUI 入口同步交付。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'B1: 結構化動作日誌'`。

### Task B2: 自愈比較與候選修正

**Files:** 修改：`je_auto_control/utils/self_healing/heal_log.py`、`je_auto_control/utils/self_healing/locator.py`、`je_auto_control/gui/self_healing_tab.py`；新增：`je_auto_control/utils/self_healing/evaluation.py`、`benchmarks/self_healing`；測試：`test/unit_test/headless/test_self_healing_evaluation.py`。

**Interfaces:** `EvaluationSample` 定義 frame/expected_box/origin/scale；`evaluate_locators(samples: Sequence[EvaluationSample], versions: Mapping[str, LocatorStrategy]) -> HealingComparison`；report 帶分子分母與 p50/p95。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_unlabelled_is_unknown, test_false_positive_is_not_recovery, test_same_frame_versions_are_comparable, test_region_passed_to_both_strategies`，驗證：

```python
assert report.unknown == 1
assert report.correct == 1 and report.false_positive == 1
assert image_region == vlm_region
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_self_healing_evaluation.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** HealEvent 增 optional version/context 欄位，讀舊格式；單一 capture 供策略比較，命中與操作後驗證分離。加入固定失敗／縮放／負座標資料集，candidate template revision 可 preview/accept/revert。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'B2: 自愈比較與候選修正'`。

### Task B3: 從日誌產生候選腳本

**Files:** 修改：`je_auto_control/utils/codegen/codegen.py`、`je_auto_control/cli.py`、`je_auto_control/gui/recording_editor_tab.py`、`je_auto_control/gui/script_builder/builder_tab.py`、`je_auto_control/utils/mcp_server/tools/_handlers_qa.py`；新增：`je_auto_control/utils/codegen/journal_import.py`；測試：`test/unit_test/headless/test_codegen_from_journal.py`。

**Interfaces:** `generate_candidate_from_log(path: Path, *, run_id: str, target: str = 'pytest', style: str = 'actions') -> CandidateScript`；包含 code、manifest、warnings。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_run_filter_and_provenance, test_observed_branch_is_labelled, test_secret_reference_survives_codegen, test_generation_has_no_device_effect`，驗證：

```python
assert candidate.manifest['run_id'] == selected_run
assert candidate.observed_path_only is True
assert device_calls == []
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_codegen_from_journal.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 驗證 JSONL schema，重建 step/parent 與 retries，控制流程不足時標示 observed path。呼叫既有 generate_code，產物 AST/command/dry-run 驗證，GUI diff 與匯入 builder、CLI --from-log 同步交付；不解析任意 repr 執行。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'B3: 從日誌產生候選腳本'`。
