Menu-Driven GUI: the Actions Menu Replaces In-Tab Buttons
=========================================================

The main window is redesigned around a menu bar and a low-button tab layout.
Tabs keep only their inputs, tables, and result/status views; every tab's
commands move to one predictable place — a window-level **Actions** menu that
rebuilds for the active tab.

The Actions menu
----------------

Two ways a tab surfaces its commands:

* **Registry actions** — core tabs (Auto Click, Screenshot, Image Detection,
  Record, Script Executor, Report) declare ``(label_key, handler)`` pairs when
  they are registered in ``gui/main_widget.py``.
* **The** ``menu_actions()`` **hook** — feature tabs expose a
  ``menu_actions()`` method returning the same ``[(label_key, handler), ...]``
  shape; the menu bar queries the active tab and renders whatever it returns.

46 of 48 registered tabs surface their commands this way. **Script Builder**
and **Remote Desktop** intentionally keep their interactive panel layouts, and
the Actions menu shows a placeholder there. Controls a window-level menu cannot
replace stay in place: per-page browse buttons inside stacked trigger forms,
the visibility-toggled data-source browse button, and stateful auto-refresh
checkboxes.

The navigation panel
--------------------

Every registered tab is listed on the left of the window, grouped by the same
five categories, whether it is open or not; open tabs are shown in bold.
Click a feature to open it (or bring it to the front). The search box filters
the list as you type — by title, by key (``usb_devices``) or by category — and
**Return** opens the first match. ``Ctrl+K`` (**View → Search Features...**)
puts the cursor in the search box from anywhere, and ``Ctrl+B``
(**View → Navigation Panel**) hides or shows the panel.

A tab is built the first time it is on screen. The window starts with three
tabs in its bar — Record, Script Builder and Remote Desktop — and Record in
front; the other two are built on the first click, and every other tab when
you open it. Nothing of Script Builder or Remote Desktop (which loads the
WebRTC stack) is imported before that.

Small windows, and what the window remembers
--------------------------------------------

A page keeps its minimum size: in a window too small for it, the tab shows
scroll bars instead of squeezing the form. Remote Desktop already scrolls its
own content and is left as it is. For code that embeds
``AutoControlGUIWidget``, ``widget.tabs`` still speaks in pages —
``tabs.indexOf(page)``, ``tabs.widget(index)``, ``tabs.currentWidget()`` and
``tabs.setCurrentWidget(page)`` take and return the tab's own widget, not the
scroll area around it.

The theme, the text size, whether the navigation panel is shown and how wide
it is, and the window's position and size are kept between runs in
``~/.je_auto_control/gui_settings.ini``. Set ``JE_AUTOCONTROL_GUI_SETTINGS``
to another file to keep them elsewhere, or to ``off`` to remember nothing
(the test suite runs that way).

Closing a tab keeps its widget, so reopening it shows it as you left it.
``AutoControlGUIWidget.close_tab(key, release=True)`` lets go of it instead:
the widget's optional ``dispose()`` method is called — the place for a tab to
stop its timers and threads and drop its listeners — the widget is deleted,
and the next ``open_tab(key)`` builds a new one. The forms the main widget
builds for itself (Auto Click, Screenshot, Image Detection, Record, Script,
Report) are closed but never released.

Every tab that holds something beyond its widgets implements ``dispose()``:
Scheduler, Triggers, Hotkeys, E-mail Triggers, Webhooks, REST API, Presence,
Live HUD, Inspector, Profiler, Run History, Admin Console, USB Devices, USB
Sharing, Config Sync and Remote Desktop, and every tab that runs a command in
the background (Script Builder, VLM, OCR, LLM Planner, Computer Use, DAG, Self
Healing, Test Suite, Assertions, Device Matrix, Mobile, Media Checks,
WebRunner, ChatOps, USB Browser, Accessibility, A11y Audit). It stops the
tab's timers, cancels its background work, removes its listener from the
presence registry, gives back its share of the USB watcher, takes its tail off
the logger and closes a loopback it opened -- on the call, not when Qt gets
round to deleting the widget. Background work is cancelled the way deleting
the tab would cancel it a moment later: a script run is stopped, a Computer
Use or DAG run is asked to stop, and work that cannot be interrupted (a model
request, a device listing) runs to its end with its answer dropped. The
backend a tab only shows (the scheduler, a REST server, a remote desktop host)
keeps running. A new tab does the same with one call,
``release_resources(self, *releases)`` from ``je_auto_control.gui._dispose``;
``test_gui_tab_dispose.py`` fails for a registered tab that creates a
``QTimer``, registers a listener or starts background work without the
method.

Remote Desktop's ``dispose()`` goes through each of its five panels. A TCP or
WebSocket host or session a panel opened is left running: it belongs to the
registry, where scripts (``AC_remote_*``) and the other panels still see it
and can stop it; only the panel's own timer, a connect that has not answered
and the pop-out window go. A WebRTC host or session belongs to its panel
alone -- with the panel gone nothing could stop it, and a host would go on
sharing the screen unseen -- so releasing the tab ends it, in the background
as the Stop command does.

A callback given to a background task is held weakly: pass a method of the
tab (or a ``functools.partial`` of one), not a lambda or a nested function
that closes over the tab. The task's handle is a child of the tab, and a
callback that kept the tab alive made the handle the last holder of a tab
nobody else referenced -- it was then destroyed from inside its own child's
destructor. ``weak_slot`` in ``je_auto_control.gui._weak_call`` makes the slot
for a handle's signal, and ``test_gui_weak_callbacks.py`` fails a new strong
one.

The View menu
-------------

* **View → Tabs** shows or hides any registered tab, grouped by category
  (Core / Editing / Detection & Vision / Automation Engines / System). The
  default layout opens with just Record, Script Builder, and Remote Desktop;
  everything else is one menu click away. Tabs are closable — closing one is
  the same as unchecking it in the View menu.
* **View → Theme** switches between the dark and the light theme. Both come
  from one set of design tokens in ``gui/theme.py``; the window no longer
  uses ``qt-material``.
* **View → Text Size** offers auto (screen-height based) and preset font
  sizes applied live, on top of the active theme.

A theme or text-size change sets the window's style sheet once and restyles
what is on screen. Qt re-applies a window's style sheet to every widget below
it, visible or not, so the pages of the tabs that are not selected are taken
out of the window's tree for the change
(``WorkspaceTabWidget.restyle(apply)``) and put back one per event-loop turn,
or at once when their tab is selected. With all 50 tabs open a switch held the
window for 1.5-1.8 s; it holds it for about 0.3 s, and the rest follows in
turns of at most 85 ms (measured with ``benchmarks/gui_workloads.py`` on the
development machine). The page of a closed tab, which is kept hidden under the
tab widget, is taken out and put back with the others.

While a page is out of the tree its ``window()`` is not the main window. Code
in a tab that needs the window it belongs to -- to raise it, or to place a
dialog -- calls ``real_window(widget)`` from
``je_auto_control.gui.workspace_tabs`` instead of ``widget.window()``.

The contract test
-----------------

``test/unit_test/headless/test_actions_menu_gui.py`` guards the contract: every
registered tab must expose commands through registry actions or a
``menu_actions()`` hook (the two exempt tabs aside), and every entry must be a
non-empty ``label_key`` string paired with a callable. A new tab that forgets
the hook fails CI instead of silently shipping with no reachable commands. The
probe runs the full widget construction in a subprocess so the Qt lifetime
cannot destabilise the rest of the headless suite.

``test/unit_test/headless/test_gui_feature_parity.py`` holds the rest: the
window opens on the three workflow tabs, every registered tab opens from the
navigation panel and fills the Actions menu, a window of 640×420 scrolls
instead of clipping, and the mixed-DPI geometry helpers agree with a
100% + 125% desktop.

Measuring the GUI
-----------------

Two scripts print a JSON report and never show a window (they run on Qt's
``offscreen`` platform and leave the GUI settings file alone):

.. code-block:: bash

   python benchmarks/gui_startup.py --runs 5 --output after.json
   python benchmarks/gui_workloads.py --output workloads.json
   python benchmarks/gui_startup.py --compare before.json after.json

``gui_startup.py`` starts the window in fresh interpreters and reports
``startup_ms`` (first line to first painted frame), its phases, and the
process's memory. ``gui_workloads.py`` opens every tab once
(``first_open_ms`` per tab), revisits them, types in the search box and
switches theme while a 5 ms timer ticks; ``event_loop_p95_ms`` is how late
those ticks arrive. ``theme_switch_ms`` is the stall of a switch,
``theme_deferred_ms`` how long the pages of the unselected tabs took to be
restyled afterwards and ``theme_deferred_longest_turn_ms`` the longest single
turn of that. ``--compare`` sets two reports side by side and refuses
when the workload or the environment differs.

Background work in a tab
------------------------

A tab that waits on a network peer or a device starts that work through
``je_auto_control.gui.task_controller`` instead of a bare thread:

.. code-block:: python

   from je_auto_control.gui.task_controller import CancellationToken, task_controller

   def fetch(url: str, token: CancellationToken) -> dict:
       token.raise_if_cancelled()
       return download(url, timeout=token.remaining(default=10.0))

   url = self._url_edit.text()                      # read the widget first
   handle = task_controller().submit(
       functools.partial(fetch, url), owner=self, timeout_s=30.0)
   handle.result.connect(self._show)                # emitted on the GUI thread
   handle.error.connect(self._show_error)           # the exception object
   handle.finished.connect(self._enable_button)     # once, whatever happened

What it adds to a plain worker:

* **Cancellation reaches the backend.** The work receives a
  ``CancellationToken``: it polls ``raise_if_cancelled()`` / ``wait()``, hands
  ``remaining()`` to a backend that takes a timeout, and registers how to let
  go of what it holds with ``on_cancel()``. ``handle.cancel()`` runs those at
  once, on the cancelling thread.
* **Typed outcomes.** ``result`` carries the return value, ``error`` the
  exception, ``progress`` whatever ``token.report_progress()`` was given. A
  timeout is reported as ``TaskTimeout``, a cancellation as ``TaskCancelled``.
* **Owner death.** The handle is a child of ``owner``. Destroying the tab
  cancels the work, and a result that arrives afterwards goes to ``discard=``
  (close the session nobody will use), never to a slot of the dead widget.
* **No worker touches a widget.** Work that is a widget's method, or closes
  over one, is refused with ``TaskUsageError`` before it starts.

A Stop that joins a thread goes through ``je_auto_control.gui._slow_op``, which
sits on the controller. ``SlowOp(self).run(backend.stop, on_done=...,
on_error=...)`` runs one such call at a time: it returns ``False`` while an
earlier one is out (a second click does nothing), ``busy`` is true until the
outcome arrives -- the tab shows "Stopping…" meanwhile -- and ``on_done`` runs
on the GUI thread once it is false again, which is where the code that used to
follow the blocking call goes. The Scheduler, Triggers, Hotkeys, E-mail
Triggers, Webhooks, REST API and USB Sharing tabs and the Remote Desktop host
panel stop (and, where a start first stops, start) this way. The WebRTC panels
let go of their session at once and hand its shutdown to a ``StopQueue``, so
the next session can start while the old one closes. Callbacks are held
weakly: pass a method and ``args=``, not a ``functools.partial`` or a lambda
that closes over the tab.

This is a GUI-internal API (it imports ``PySide6``) and is not re-exported by
the package facade; the headless functions a tab calls stay usable without it.
