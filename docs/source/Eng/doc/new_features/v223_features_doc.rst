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

The View menu
-------------

* **View → Tabs** shows or hides any registered tab, grouped by category
  (Core / Editing / Detection & Vision / Automation Engines / System). The
  default layout opens with just Record, Script Builder, and Remote Desktop;
  everything else is one menu click away. Tabs are closable — closing one is
  the same as unchecking it in the View menu.
* **View → Text Size** offers auto (screen-height based) and preset font
  sizes applied live.

The contract test
-----------------

``test/unit_test/headless/test_actions_menu_gui.py`` guards the contract: every
registered tab must expose commands through registry actions or a
``menu_actions()`` hook (the two exempt tabs aside), and every entry must be a
non-empty ``label_key`` string paired with a callable. A new tab that forgets
the hook fails CI instead of silently shipping with no reachable commands. The
probe runs the full widget construction in a subprocess so the Qt lifetime
cannot destabilise the rest of the headless suite.
