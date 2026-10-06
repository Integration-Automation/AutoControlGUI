## Summary

This Draft PR defines and tracks the Windows 2.0 architecture discussed for AutoControlGUI.

The goal is **not** to add another collection of `AC_windows_*` commands. The goal is to consolidate the existing Windows-specific capabilities into a stable platform layer that can support deterministic native automation first, with OCR/template/vision fallback above it.

### Design principles

- Keep `windows/` as the Windows platform implementation layer.
- Keep `AC_*` commands and cross-platform wrappers above the platform layer.
- Reuse and migrate existing Windows implementations; do not create parallel duplicate backends.
- Prefer semantic/native automation over coordinates:
  **UIA → TextPattern → OCR → template → vision → coordinate**.
- Treat DPI and coordinate spaces as first-class types.
- Separate locator, action, input, verification, and recovery concerns.
- Preserve backwards compatibility while the new API is introduced incrementally.

## Target architecture

```text
je_auto_control/
├── windows/
│   ├── core/
│   │   ├── handles.py
│   │   ├── errors.py
│   │   ├── constants.py
│   │   ├── structs.py
│   │   └── api.py
│   ├── window/
│   │   ├── model.py
│   │   ├── manager.py
│   │   ├── finder.py
│   │   └── geometry.py
│   ├── uia/
│   │   ├── element.py
│   │   ├── tree.py
│   │   ├── locator.py
│   │   ├── patterns.py
│   │   ├── events.py
│   │   └── backend.py
│   ├── input/
│   │   ├── mouse.py
│   │   ├── keyboard.py
│   │   ├── sendinput.py
│   │   ├── interception.py
│   │   └── strategy.py
│   ├── screen/
│   │   ├── monitor.py
│   │   ├── dpi.py
│   │   ├── capture.py
│   │   └── coordinates.py
│   ├── process/
│   │   ├── process.py
│   │   ├── launcher.py
│   │   └── wait.py
│   ├── clipboard/
│   │   ├── text.py
│   │   ├── formats.py
│   │   └── watcher.py
│   ├── shell/
│   │   ├── explorer.py
│   │   ├── dialogs.py
│   │   ├── taskbar.py
│   │   └── start_menu.py
│   └── console/
│       ├── powershell.py
│       ├── cmd.py
│       └── terminal.py
├── wrapper/
└── utils/
```

The exact file split may be adjusted during implementation to match existing project conventions. The architectural boundaries are the important part.

## Public API contracts

### WindowsContext

```python
class WindowsContext:
    @property
    def windows(self) -> WindowManager: ...
    @property
    def uia(self) -> UIAutomation: ...
    @property
    def input(self) -> InputManager: ...
    @property
    def screen(self) -> ScreenManager: ...
    @property
    def clipboard(self) -> ClipboardManager: ...
    @property
    def processes(self) -> ProcessManager: ...
```

### Window / WindowManager

```python
@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process_id: int
    thread_id: int
    rect: Rect
    visible: bool
    minimized: bool
    maximized: bool

class Window:
    def activate(self) -> None: ...
    def close(self) -> None: ...
    def minimize(self) -> None: ...
    def maximize(self) -> None: ...
    def restore(self) -> None: ...
    def move(self, x: int, y: int) -> None: ...
    def resize(self, width: int, height: int) -> None: ...
    def move_resize(self, rect: Rect) -> None: ...
    def screenshot(self): ...

class WindowManager:
    def list(self) -> list[Window]: ...
    def active(self) -> Window | None: ...
    def find(...): ...
    def find_all(...): ...
    def wait_for(...): ...
```

### UIElement

Expose normalized UIA properties:

- name
- automation_id
- control_type
- class_name
- bounds
- enabled
- visible
- focused
- value

Expose native UIA patterns where supported:

- Invoke
- Value
- Toggle
- Selection / SelectionItem
- ExpandCollapse
- Scroll
- RangeValue
- Grid / Table
- Text
- Window

Examples:

```python
element.invoke()
element.set_value("hello")
element.toggle()
element.select()
element.expand()
element.collapse()
element.scroll(...)
```

### Locator

Support deterministic selectors:

- AutomationId
- Name
- ControlType
- ClassName
- parent/child relationships
- index where required

And semantic relations:

```python
locator.parent()
locator.child(...)
locator.sibling(...)
locator.above()
locator.below()
locator.left()
locator.right()
locator.near()
locator.inside()
```

### Input

Use an explicit strategy layer:

```text
InputManager
├── Native / SendInput
├── Low-level / Interception
└── Virtual / HID / ViGEm where applicable
```

The automatic strategy must report the backend actually used rather than silently hiding fallback behavior.

### Coordinates / DPI

Define explicit coordinate spaces:

- SCREEN_PHYSICAL
- SCREEN_LOGICAL
- WINDOW
- MONITOR
- NORMALIZED

All conversions must be explicit and tested for:

- 100% DPI
- non-100% DPI
- multi-monitor
- negative monitor origins

### Process / Clipboard

Process lifecycle:

```python
app = processes.launch("foo.exe")
app.wait_for_window(...)
app.windows()
app.close()
```

Clipboard:

```python
clipboard.get_text()
clipboard.set_text(...)
clipboard.clear()
clipboard.wait_for_change(...)
clipboard.preserve()
```

## Action / verification direction

Introduce a result object that can carry:

- success
- action
- backend
- duration
- target
- error
- metadata

Actions should eventually support explicit verification:

```text
Action
  ↓
Verify
  ↓
Retry
  ↓
Recovery
  ↓
Trace / Report
```

Example:

```python
button.invoke(
    verify=TextAppeared("Saved")
)
```

This is intentionally a later phase; the first implementation should establish the platform contracts without coupling the Windows layer to the full workflow engine.

## Implementation roadmap

### Phase A — Windows Foundation

- [ ] **PR 1 — Windows Core Contract**
  - [ ] common Win32 handle/types
  - [ ] Rect / Point / Size
  - [ ] Windows-specific exceptions
  - [ ] ctypes/constants boundary
- [ ] **PR 2 — Window Manager**
  - [ ] WindowInfo
  - [ ] enumerate/find/active/wait
  - [ ] activate/close/minimize/maximize/restore
  - [ ] move/resize
  - [ ] migrate existing window operations without breaking compatibility
- [ ] **PR 3 — DPI / Monitor / Coordinates**
  - [ ] monitor enumeration
  - [ ] DPI awareness/conversion
  - [ ] explicit coordinate spaces
  - [ ] multi-monitor and negative-origin tests
- [ ] **PR 4 — UIA Element Model**
  - [ ] normalized UIElement
  - [ ] UIA tree access
  - [ ] UIA property access
  - [ ] UIA Pattern adapters
  - [ ] migrate/reuse current Windows accessibility backend

### Phase B — Windows Automation

- [ ] **PR 5 — Unified UIA Locator**
  - [ ] selector object
  - [ ] deterministic property matching
  - [ ] parent/child/sibling relations
  - [ ] relative/semantic locators
  - [ ] TextPattern before OCR
- [ ] **PR 6 — Native Input**
  - [ ] InputManager
  - [ ] SendInput backend
  - [ ] existing low-level input integration
  - [ ] strategy/fallback reporting
  - [ ] backwards-compatible wrappers
- [ ] **PR 7 — Process / Application**
  - [ ] process enumeration
  - [ ] launch/wait/terminate/kill
  - [ ] process-to-window binding
  - [ ] wait_for_window
- [ ] **PR 8 — Clipboard / Windows Shell**
  - [ ] clipboard API
  - [ ] clipboard preservation
  - [ ] Explorer
  - [ ] file open/save dialogs
  - [ ] Start Menu / Taskbar where practical

### Phase C — Reliable Computer Use

- [ ] **PR 9 — ActionResult / Verification**
  - [ ] ActionResult
  - [ ] verification primitives
  - [ ] explicit retry
  - [ ] recovery hooks
  - [ ] trace/report integration
- [ ] **PR 10 — Wrapper / AC_* integration**
  - [ ] expose stable Windows APIs through existing wrapper layer
  - [ ] add AC_* adapters only where they are useful
  - [ ] keep business logic out of AC_* commands
- [ ] **PR 11 — Windows Events**
  - [ ] UIA events
  - [ ] window created/destroyed
  - [ ] focus changed
  - [ ] property/structure changes
  - [ ] event-driven waits
- [ ] **PR 12 — Semantic fallback**
  - [ ] UIA → TextPattern → OCR → template → vision → coordinate
  - [ ] locator diagnostics
  - [ ] self-healing locator strategy

## Migration rules

1. Do not duplicate an existing Windows implementation merely to fit the new tree.
2. Prefer adapters first, followed by incremental extraction/refactoring.
3. Existing `wrapper/`, `AC_*`, accessibility and input APIs remain compatible during migration.
4. `windows/` must not depend on `AC_*` command definitions.
5. UIA should expose semantic operations; raw mouse input belongs to the input layer.
6. Vision/OCR must not become the default path when deterministic Windows APIs can provide the same information.
7. Every fallback that changes execution semantics must be observable in the action/result trace.

## Acceptance criteria

### Architecture

- [ ] Windows-specific code has clear ownership under `windows/`.
- [ ] No new generic `utils.py` / catch-all manager is introduced for the new layer.
- [ ] Platform implementation does not import or depend on `AC_*` commands.

### Compatibility

- [ ] Existing public Windows automation APIs continue to work.
- [ ] Existing wrapper/AC integrations can delegate to the new layer incrementally.
- [ ] No unnecessary duplicate Win32/UIA implementations are introduced.

### Reliability

- [ ] Window lookup supports deterministic properties.
- [ ] UIA elements expose normalized state.
- [ ] DPI and monitor coordinate conversions are tested.
- [ ] Input backend selection is observable.
- [ ] Wait APIs have bounded timeouts and useful errors.

### Testing

- [ ] Unit tests for pure models/selectors.
- [ ] Windows integration tests for HWND/UIA/window lifecycle.
- [ ] DPI/multi-monitor test coverage where the CI environment permits.
- [ ] Existing headless suite remains green.
- [ ] New Windows-only tests are skipped or gated cleanly outside Windows.

## Out of scope for the first implementation

- Replacing the existing vision/AI stack.
- Rewriting all existing `AC_*` commands.
- Building a second cross-platform automation abstraction.
- Making every Windows feature available through GUI tabs immediately.
- Making vision the primary Windows locator.

## Definition of done for the architecture phase

The architecture phase is complete when a caller can reliably express:

```python
windows = WindowsContext()

app = windows.processes.launch("myapp.exe")
window = app.wait_for_window(title="My Application")

button = windows.uia.find(
    window=window,
    name="Login",
    control_type="Button",
)

button.invoke()
```

and the implementation is backed by the new Windows platform layer rather than a new collection of one-off `AC_*` commands.

---

**Status:** Draft / architecture + implementation plan

**Next recommended change:** start with PR 1 (Windows Core Contract), then PR 2–4 as the first implementation wave.