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
those ticks arrive. ``--compare`` sets two reports side by side and refuses
when the workload or the environment differs.
