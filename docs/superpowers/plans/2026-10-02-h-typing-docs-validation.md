# H：型別深化、完整文件與總驗收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native execution, or superpowers:subagent-driven-development if the user chooses delegation. Steps use checkbox syntax for tracking.

**Goal:** 驗證全套型別契約、所有新流程文件與平台功能矩陣一致。

**Architecture:** 依核准設計做獨立可測的增量交付，沿用 headless → executor → GUI/MCP 邊界。各階段都更新文件與型別；本計畫做跨階段的最終驗收。

**Tech Stack:** mypy、ruff、bandit、radon、coverage、Sphinx、既有 CI

**Spec:** [核准設計](../specs/2026-10-02-platform-gui-modernization-design.md)

## Global Constraints

- Python ≥3.10；新檔 ≤750 行；公開 API 有 docstring 與型別；例外屬 AutoControlException。
- 保留 import、AC_* 名稱與舊 CLI 旗標；headless import 不載入 Qt；相依延遲匯入。
- 一般 GUI 面板操作經 Actions menu；重寫模組不得擴大 mypy 豁免或全域忽略。
- `architecture.md`、`architecture_explore.md`、三語 README、對應 Sphinx 文件與 `docs/updates/` 隨交付更新；僅完成的 Progress 條目才刪除。
- 測試使用受控輸入、不操作使用者桌面；有實機證據才標示實機已驗證。

## Review Focus

- 安裝 GUI/行動 extras 後仍要維持 type gate 意義。
- 文件指令不能只在某位開發者機器可用。
- 離線例子不能在 validate 時操作桌面。
- fake/device smoke 不等於實機驗證。
- 下游 editable install 不能被測試环境導到另一份套件。

## 驗證與提交規則

每個 task 先加重現測試、確認失敗、實作、確認成功、更新相關文件並逐檔提交。
下列 assertion snippets 的測試資料與 fake fixtures 在同一測試模組定義，不能修改 assertion 迎合實作。
Step 4 通過後，該階段另外執行 ruff、相關既有回歸與三目標型別 gate；全面 coverage 與平台 smoke 於整合階段執行。
檔案列出的既有目錄是要逐項檢查的入口；新增模組名稱與以下接口固定，搬移時保留兼容路徑。

---

### Task H1: 型別檢查深度與相依矩陣

**Files:** 修改：`pyproject.toml`、`test/verify/typing_contract_verify.py`、`test/verify/typing_contract_exempt.txt`、`.github/workflows/quality.yml`；測試：`test/unit_test/headless/test_typing_modernization_contract.py`。

**Interfaces:** 新／重寫模組限定 disallow_untyped_defs、disallow_any_generics；win32/linux/darwin 目標維持，extras 型別檢查另列 job。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_exemptions_remain_empty, test_new_modules_have_complete_annotations, test_adapter_is_only_sdk_any_boundary`，驗證：

```python
assert exemptions == set()
assert untyped_public_signatures == []
assert sdk_any_leaks == []
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_typing_modernization_contract.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 為 SDK 邊界建立 Protocol/typed adapters，新增 py-modules 也加入範圍。不要 blanket skip GUI；保留確實無法被3.10解析的依賴特定理由，空豁免不變。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'H1: 型別檢查深度與相依矩陣'`。

### Task H2: 完整範例與三語文件

**Files:** 修改：`examples/README.md`、`README.md`、`README/README_zh-TW.md`、`README/README_zh-CN.md`、`docs/CAPABILITY_MATRIX.md`、`docs/API_LIFECYCLE.md`、`docs/source/Eng`、`docs/source/Zh`；新增：`examples/28_wayland_diagnostics.py`、`examples/29_config_sync.py`、`examples/30_mobile_devices.py`、`examples/31_healing_comparison.py`、`examples/32_codegen_from_log.py`、`examples/33_mcp_progressive.py`；測試：`test/unit_test/headless/test_modernization_examples.py`。

**Interfaces:** 每個 example 提供 --validate 或可無副作用的測試入口；功能矩陣由能力 metadata 校對；範例數由既有測量 gate 更新。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_examples_compile_and_validate_without_device, test_readme_configuration_parity, test_matrix_matches_capabilities`，驗證：

```python
assert device_effects_in_validate == []
assert translated_configuration_keys == english_configuration_keys
assert undocumented_capabilities == set()
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_modernization_examples.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** 交付安裝、啟動、權限、GUI操作、headless與CLI/MCP、故障與遷移完整流程。Sphinx 引用 shared examples，三README一致，API lifecycle標示兼容／新format，所有計數重新量測。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'H2: 完整範例與三語文件'`。

### Task H3: 跨平台、下游與發布前回歸

**Files:** 修改：`.github/workflows/platform-smoke.yml`、`.github/workflows/quality.yml`、`test/verify/macos_verify.py`、`test/integrated_test`、`architecture.md`、`architecture_explore.md`、`Progress.md`、`docs/updates/README.md`；測試：`test/unit_test/headless/test_modernization_integration.py`。

**Interfaces:** integration reports 帶 platform/backend/version、actual/skipped reason；只在測試證據存在時移除 Progress 對應條目。

- [ ] **Step 1:** 定義 fake fixtures 並新增 `test_journal_to_script_to_device_result, test_sync_restart_and_gui_session, test_platform_capability_report_has_evidence`，驗證：

```python
assert replay_report.source_steps == manifest.source_steps
assert reopened_sync.revision == committed_revision
assert all_verified_capabilities_have_evidence is True
```

- [ ] **Step 2:** 執行 `.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.test-tmp/modernization-task -o cache_dir=.test-tmp/modernization-pytest-cache test/unit_test/headless/test_modernization_integration.py`，確認新測試因原有缺陷或尚未提供接口而 FAIL；不要把環境錯誤當成功的重現。
- [ ] **Step 3:** Python3.10–3.14與各OS CI、現有coverage floor不下降；手動／CI native EI、GNOME/KDE、Retina、Android、iOS結果附文件。執行下游 test_gui_facade/test_gui_control 與跨專案契約；有阻礙寫進 Progress，不能假完成。
- [ ] **Step 4:** 重跑 Step 2，預期 exit 0；再跑這些修改檔所對應的既有回歸，確認公開契約。
- [ ] **Step 5:** 更新本 task 的型別、所有交付入口、文件、測量計數與進度，僅 stage 本 task 檔案，提交 `git commit -m 'H3: 跨平台、下游與發布前回歸'`。
