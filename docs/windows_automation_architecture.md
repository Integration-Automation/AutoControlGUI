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

## Detailed API and implementation examples

### Module responsibilities

| Module | Responsibility | Must not own |
|---|---|---|
| windows/core | Win32 ctypes, handles, constants, structs, low-level errors | workflow logic |
| windows/window | HWND discovery, lifecycle, geometry, activation | UIA pattern implementation |
| windows/uia | UI Automation tree, elements, selectors, patterns, events | raw mouse/keyboard injection |
| windows/input | mouse/keyboard input and backend selection | UI tree discovery |
| windows/screen | monitors, DPI, capture, coordinate conversion | application semantics |
| windows/process | process lifecycle and application binding | UI element operations |
| windows/clipboard | clipboard formats, preservation, watchers | workflow orchestration |
| windows/shell | Explorer, dialogs, Start Menu, Taskbar | generic UIA primitives |
| windows/console | CMD, PowerShell, Windows Terminal | arbitrary workflow logic |
| wrapper | cross-platform facade and compatibility | Win32 implementation details |
| executor / AC_* | command/workflow dispatch | Windows backend implementation |

The Windows platform layer provides capabilities; the automation layer decides when and why to use them.

### Window example

~~~python
windows = WindowsContext()

window = windows.windows.find(title="Calculator")
window.activate()

if not window.is_active:
    raise WindowActivationError(window.hwnd)

window.move_resize(Rect.from_xywh(100, 100, 800, 600))
~~~

Multiple discovery strategies:

~~~python
window = windows.windows.find(
    title="Calculator",
    class_name="ApplicationFrameWindow",
)

window = windows.windows.find(process_name="calc.exe")

window = windows.windows.wait_for(
    title_regex=r".*Calculator.*",
    timeout=10.0,
)
~~~

### UIA-first interaction

~~~python
app_window = windows.windows.wait_for(
    title="My Application",
    timeout=10,
)

button = windows.uia.find(
    window=app_window,
    name="Login",
    control_type="Button",
)

assert button.enabled
button.invoke()
~~~

Text fields should prefer ValuePattern:

~~~python
username = windows.uia.find(
    window=app_window,
    automation_id="Username",
    control_type="Edit",
)

username.set_value("user@example.com")
~~~

Checkboxes:

~~~python
remember_me = windows.uia.find(
    window=app_window,
    name="Remember me",
    control_type="CheckBox",
)

remember_me.toggle()
~~~

Tree/list navigation:

~~~python
settings = windows.uia.find(
    window=app_window,
    name="Settings",
    control_type="TreeItem",
)

settings.expand()

notifications = settings.child(
    name="Notifications",
    control_type="TreeItem",
)

notifications.select()
~~~

### UIA Pattern fallback

~~~python
if element.supports("Value"):
    element.set_value("hello")
else:
    element.type_text("hello")
~~~

Preferred execution order:

~~~text
native UIA pattern
    ↓ unavailable
native semantic/text operation
    ↓ unavailable
keyboard input
    ↓ unavailable
mouse input
    ↓ unavailable
OCR / template / vision fallback
~~~

Unsupported operations should raise a specific exception instead of silently reporting success.

### Locator composition

~~~python
login_button = (
    windows.uia.selector()
    .inside(window)
    .child(
        control_type="Pane",
        automation_id="LoginPanel",
    )
    .descendant(
        name="Login",
        control_type="Button",
    )
    .first()
)

login_button.invoke()
~~~

Relative locators:

~~~python
password = windows.uia.find(
    window=window,
    automation_id="Password",
)

show_password = password.right(
    name="Show password",
    control_type="CheckBox",
)

show_password.toggle()
~~~

Relative relations should use UIA tree/bounds information whenever possible, not hard-coded screen coordinates.

### State-based waits

Avoid arbitrary sleeps:

~~~python
time.sleep(2)
pyautogui.click(123, 456)
~~~

Prefer state-based waits:

~~~python
button = windows.uia.wait_for(
    window=window,
    name="Continue",
    control_type="Button",
    timeout=10,
)

button.invoke()

windows.uia.wait_for(
    window=window,
    name="Completed",
    control_type="Text",
    timeout=10,
)
~~~

### ActionResult

~~~python
@dataclass
class ActionResult:
    success: bool
    action: str
    backend: str
    duration: float
    target: str | None = None
    error: Exception | None = None
    metadata: dict[str, object] = field(default_factory=dict)
~~~

Example:

~~~python
result = button.invoke()

if not result.success:
    logger.error(
        "UI action failed: backend=%s target=%s error=%s",
        result.backend,
        result.target,
        result.error,
    )
~~~

The result should be serializable into the existing trace/failure-bundle infrastructure.

### Input backend strategy

~~~text
InputManager
├── Native / SendInput
├── Low-level / Interception
└── Virtual / HID / ViGEm
~~~

The strategy must report the actual backend used:

~~~python
result = windows.input.click(point, strategy="auto")

assert result.backend in {
    "sendinput",
    "interception",
    "virtual",
}
~~~

A backend failure must remain observable rather than being silently swallowed.

### DPI and coordinate model

The new layer should never pass an untyped (x, y) between unrelated coordinate spaces.

~~~python
Point(
    x=100,
    y=200,
    space=CoordinateSpace.SCREEN_PHYSICAL,
)
~~~

Conversions:

~~~python
physical = screen.to_physical(logical_point)
logical = screen.to_logical(physical_point)

window_point = window.to_window(screen_point)
screen_point = window.to_screen(window_point)
~~~

Required test scenarios:

- 100% DPI
- 125% DPI
- 150% DPI
- mixed-DPI monitors
- secondary monitor to the right
- secondary monitor to the left (negative X)
- monitor above primary (negative Y)
- per-monitor DPI awareness

Monitor diagnostics:

~~~python
for monitor in windows.screen.monitors():
    print(
        monitor.id,
        monitor.bounds,
        monitor.work_area,
        monitor.dpi,
        monitor.scale,
        monitor.is_primary,
    )
~~~

### Process / window binding

A process and a window are related but must remain separate abstractions:

~~~python
app = windows.processes.launch(
    "C:/Program Files/MyApp/MyApp.exe",
    args=["--automation"],
)

window = app.wait_for_window(
    title="My Application",
    timeout=15,
)

assert window.process_id == app.pid
~~~

This supports applications with multiple top-level windows:

~~~text
Process
├── Main Window
├── Dialog
└── Child Window
~~~

The process layer owns lifecycle; window/UIA layers own interaction.

### Clipboard

~~~python
with windows.clipboard.preserve():
    windows.clipboard.set_text("automation text")
    value = windows.clipboard.get_text()
~~~

Watching changes:

~~~python
with windows.clipboard.watch() as changes:
    windows.input.hotkey("ctrl", "c")
    change = changes.wait(timeout=3)
    print(change.text)
~~~

When another process holds the clipboard, behavior should be bounded retry/wait plus a useful error, not an indefinite hang.

### Windows Shell

~~~python
windows.shell.explorer.open(
    path=r"C:\Users\Public\Documents"
)

windows.shell.dialogs.open_file(
    title="Open configuration",
    path=r"C:\config.json",
)

windows.shell.dialogs.save_file(
    title="Save result",
    path=r"C:\output.json",
)
~~~

Internally these may use UIA, Win32, Shell APIs, or input depending on the operation.

### Console / Terminal

Distinguish process execution from terminal UI automation:

~~~python
result = windows.console.powershell.run(
    "Get-Process | Select-Object -First 5"
)

result = windows.console.cmd.run(
    ["ipconfig", "/all"]
)
~~~

### Event-driven automation

Target events:

~~~text
UIA
├── FocusChanged
├── PropertyChanged
├── StructureChanged
└── AutomationEvent

Window
├── Created
├── Destroyed
├── Activated
├── Minimized
└── Restored

Process
├── Started
└── Exited
~~~

Example:

~~~python
with windows.uia.events.focus_changed() as events:
    button.invoke()
    focused = events.wait(timeout=5)

assert focused.name == "Username"
~~~

### Verification and recovery

~~~text
Locate
  ↓
Actionability check
  ↓
Action
  ↓
Verify effect
  ↓
Success
~~~

Failure path:

~~~text
Action failed
      ↓
Collect diagnostics
      ↓
Retry same strategy
      ↓
Try alternate locator
      ↓
Try alternate backend
      ↓
OCR/template/vision fallback
      ↓
Return structured failure
~~~

Example:

~~~python
result = button.invoke(
    verify=lambda: windows.uia.exists(
        window=window,
        name="Logged in",
    ),
)

if not result.success:
    result = button.retry(
        max_attempts=2,
        alternate_locator=True,
    )
~~~

Self-healing must never silently change workflow semantics. Every fallback must be recorded.

### Locator priority

~~~text
1. UIA AutomationId
2. UIA Name + ControlType
3. UIA ClassName / structural relation
4. UIA TextPattern / native pattern
5. OCR / text
6. Template matching
7. Vision model
8. Absolute coordinates
~~~

Coordinates are an emergency fallback, not the primary automation interface.

## Architecture rules / anti-patterns

Do not create one AC command for every Windows primitive.

Bad:

~~~text
AC_windows_click
AC_windows_click_at
AC_windows_click_hwnd
AC_windows_click_uia
AC_windows_click_interception
AC_windows_click_retry
AC_windows_click_verified
~~~

Better:

~~~python
windows.uia.find(...).invoke()
windows.input.click(...)
~~~

Do not mix UIA and raw input responsibilities.

Bad:

~~~python
UIAElement.click()
    -> hidden global mouse implementation
~~~

Better:

~~~python
UIAElement.invoke()
~~~

for semantic InvokePattern, or explicitly:

~~~python
windows.input.click(element.bounds.center)
~~~

when a pointer action is actually required.

Do not make vision the Windows default. Do not create a generic Windows mega-manager. Keep cohesive services:

~~~text
windows.windows
windows.uia
windows.input
windows.screen
windows.processes
windows.clipboard
windows.shell
windows.console
~~~

## Dependency graph and first PR sequence

~~~text
PR 1  Windows Core Contract
          │
          ├── PR 2  Window Manager
          ├── PR 3  DPI / Monitor / Coordinates
          └── PR 4  UIA Element Model
                    │
                    └── PR 5  Unified Locator
                              │
             ┌────────────────┼────────────────┐
             │                │                │
          PR 6 Input       PR 7 Process     PR 8 Shell
             │                │                │
             └────────────────┼────────────────┘
                              │
                       PR 9 Verification
                              │
                       PR 10 AC / Wrapper
                              │
                       PR 11 Events
                              │
                       PR 12 Self-healing
~~~

### PR 1 — Windows Core Contract

Only reusable primitives:

~~~text
HWND
HMONITOR
ProcessId
Rect
Point
Size
Dpi
CoordinateSpace
WindowsError
~~~

No workflow code.

### PR 2 — Window Manager

~~~python
window = windows.windows.find(...)
window.activate()
window.move_resize(...)
window.close()
~~~

### PR 3 — DPI / Monitor

Make all geometry code use the coordinate model before UIA/input grows on top of it.

### PR 4 — UIA Element Model

~~~python
root = windows.uia.root(window)
elements = root.children()
~~~

### PR 5 — Unified Locator

~~~python
windows.uia.find(
    window=window,
    automation_id="submitButton",
)
~~~

### PR 6 — Input

Move native input implementations behind one strategy interface without making UIA depend on them.

### PR 7 — Process

Connect application lifecycle with window discovery.

### PR 8 — Clipboard / Shell

Add common Windows automation primitives that otherwise get duplicated across commands.

### PR 9 — Verification

Introduce structured success/failure and post-action state checks.

### PR 10 — AC / Wrapper Integration

Only after the platform API is stable should existing command layers migrate.

### PR 11 — Events

Replace unnecessary polling with native UI/process/window events.

### PR 12 — Self-healing

Add controlled fallback and diagnostics after deterministic paths are reliable.

## Testing strategy

Three levels are required.

### Unit tests

~~~text
Rect
Point
CoordinateSpace
Selector
Locator composition
ActionResult
retry policy
~~~

### Windows integration tests

~~~text
HWND enumeration
window activation
window geometry
DPI conversion
UIA tree
UIA patterns
process lifecycle
clipboard
input
~~~

### End-to-end tests

~~~text
launch application
    ↓
find window
    ↓
find UIA element
    ↓
perform action
    ↓
verify state
    ↓
collect diagnostics on failure
~~~

Prefer stable fixture applications over arbitrary third-party software.

## Compatibility / migration policy

~~~text
Existing implementation
        │
        ▼
Adapter
        │
        ▼
New windows/* API
        │
        ▼
Existing wrapper / AC_*
~~~

No first-phase PR should require a flag-day rewrite.

## Final architecture

~~~text
AutoControlGUI
│
├── Python API
├── AC_* / Workflow DSL
└── Automation Core
    │
    ├── Locator
    │   ├── UIA
    │   ├── TextPattern
    │   ├── OCR
    │   ├── Template
    │   └── Vision
    │
    └── Action
        ├── UIA Patterns
        ├── Input
        ├── Window
        ├── Process
        ├── Clipboard
        └── Shell
             │
             ▼
       Windows Platform Layer
       ├── Win32
       ├── UIA
       ├── Process
       ├── Input Backends
       ├── Screen / DPI
       └── Native Windows APIs
~~~

The key architectural rule is:

> Find the UI element → confirm it is actionable → perform the action → verify that the state actually changed → if necessary, change locator/backend/strategy and retry → report the complete trace.


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