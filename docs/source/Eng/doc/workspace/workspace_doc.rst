GUI workspace
=============

Lazy panels
-----------

Startup opens Record, Script Builder and Remote Desktop. View → Tabs keeps all
50 feature keys available; other modules/widgets are imported/created on first
open. Action metadata stays passive and handlers bind after construction. Missing
optional dependencies display recovery instructions without hiding the feature.

Legacy ``AutoControlGUIWidget`` imports and show/hide/list/core methods remain
compatible. ``hide_tab`` preserves entered data; the tab close button or
``close_tab`` releases/deletes the panel and subscriptions. Reopening a closed
panel creates a fresh widget under the same key. Catalog ordering and
key/title/visible/category list fields are preserved. Language/engine refresh
touches only constructed panels. GUI factories/open/close run on the GUI thread;
``gui.tab_registry`` metadata can be imported without Qt or feature construction.

Offscreen tests explicitly open every feature for the Actions audit and verify
unopened imports, hide/reveal identity and deferred listener cleanup. These tests
do not establish physical input or native state restoration.

Navigation and presentation
---------------------------

The left navigation searches every feature key, current translation and English
alias without running factories. Ctrl+K selects the search; Enter opens the first
match, Down moves to the result tree. The existing Actions menu runs operations.
The middle workspace reuses the registry owner and retains tab inputs. Execution
details on the right display explicit empty/ready/busy/error/permission/dependency/
unsupported states, reasons, recovery and reported progress. Ready describes the
workspace, not verified native permissions. Task cancellation follows the lifecycle below.

Ctrl+Shift+D or View toggles details. Below 900 logical pixels details collapse by
default; explicit toggles override this. Wide content remains scrollable at
640×480. View → Theme changes light/dark; Text Size uses system fonts. Four-language
refresh preserves search, active identity and existing inputs. Missing dependency
recovery refreshes its labels too. Native Qt icons and focus outlines require no
new image/theme package. ``benchmarks/gui_workspace_capture.py`` produces actual
Qt offscreen screenshots; optional ``--font`` supplies installed fonts where the
offscreen platform discovers none. The recorded Windows/Python/PySide/layout report
is in ``benchmarks/results/gui-workspace-f2``. Native multi-monitor DPI is H3.

Cancellation and owned resources
--------------------------------

Actions → Cancel current task revokes the selected panel's work; close drops late
owner/run/session delivery. TaskController carries typed result/error/progress,
a deadline and cancellation Event. Nested sleeps wake promptly, and new actions
stop at checkpoints. Slow device/network/capture/recognition/service-stop work runs
off Qt. An in-flight native call must return within its backend limit; cancellation
cannot undo completed file, vault or global-service operations. Shared services
still need their explicit Stop action.

GUI recording owns an independent recorder or X11 subscription and preserves
borrowed global recording. Raw GUI holds persist across successful runs until
release/cancel/panel destruction; cleanup only releases known owned input and
retains failures for Tools → Retry owned cleanup. Previously pressed inputs are
preserved; unknown initial state refuses allocation. Session native allocation and
close share an off-Qt gate, and failed peers/containers remain retained for retry.
These contracts do not provide atomic protection from external clients or prove
physical restoration. Direct headless input semantics remain compatible.
The full catalog I/O audit is in ``docs/GUI_TASK_LIFECYCLE.md``; native device,
GNOME/KDE permission and mixed-DPI verification remain H3.
