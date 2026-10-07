# Wayland D3 native acceptance

These are manual acceptance steps, not recorded native results. Run separately
on GNOME and KDE Wayland; controlled bus/reader tests do not replace them.
Record OS, Python, desktop/compositor and xdg-desktop-portal/backend versions,
the installed wheel/commit, selected device identity, steps and observed results.
Use a scratch editor and an idle automation session.

1. Open Diagnostics. Construction and status refresh must not open input nodes
   or show a consent dialog. Keep the GUI Stop input control action available.
2. Set the preferred trigger to F7 and invoke Actions > Request portal stop
   shortcut. Deny the consent request. Check needs_permission and the recovery
   instruction; refresh repeatedly and confirm no further request appears.
3. Invoke Close portal stop shortcut, then explicitly request again and allow.
   Record the actual trigger description chosen by the compositor. Press that
   trigger; confirm native input control stops. Holding it must produce only
   one callback until released. The registration is a stop binding, not a
   global key-state query or a recorder. Arbitrary Python work is not interrupted.
4. Leave consent unanswered and invoke Close portal stop shortcut. Confirm the
   dialog/request and owned session close. Repeat with two independently owned
   panels or Python WaylandInputSession objects; closing one must not close the
   other's stop grant or the script default. Save timing/status observations.
5. Revoke the granted shortcut or restart the portal/compositor. Confirm the
   session reports failure, signals stop and does not silently register again.
   Close/start is the explicit recovery path. Record whether the compositor
   permits registration and how its binding differs from the preference.
6. Select an existing physical USB input event node (or its by-id link) that
   the current account already has permission to read. Enter its JSON path list
   and invoke Start raw physical recording. Do not change ACLs or use elevated
   privileges as part of the test. Record the path and resolved sysfs identity.
7. Press/release a key and move the selected physical device, then invoke Stop
   raw physical recording. Inspect the raw device/event/code/value/timestamp
   fields. Motion must remain device units, never converted into a desktop
   position or fed to the legacy replay editor.
8. Repeat with a selected virtual/uinput node and with a denied physical node:
   virtual sources must not be opened; denial must name existing read access
   and retain typed needs_permission evidence. Remove a selected device during
   capture and confirm failure/cleanup, not successful partial output. Changing
   an ACL after open does not revoke the already-open Linux descriptor.
9. With a valid stop binding already registered, leave native EI input consent
   unanswered and invoke Stop input control (or activate the stop binding).
   Confirm cancellation does not wait for consent, the helper is reclaimed,
   and late completion cannot publish the cancelled grant. Explicit retry must
   create a fresh request.
10. Against a consenting native EI session, send a held Shift to the scratch
   application, close normally and verify release. In a separate attempt kill
   the EI helper and verify the compositor revokes its device and subsequent
   physical typing has no held modifier. Save the helper diagnostic and desktop
   observations. Never infer physical keyboard recovery from an EIS peer log.

For every failed step retain the artifact, observed capability state and recovery
result. Keep unresolved desktop/device cases in Progress.md and H3. Docker/EIS
worker tests cover process containment and controlled input, independently from
the desktop results above.
