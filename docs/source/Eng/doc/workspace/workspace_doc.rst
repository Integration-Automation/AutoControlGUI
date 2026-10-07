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
