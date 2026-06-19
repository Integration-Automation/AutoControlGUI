Approval Testing (Golden-Master Baselines)
==========================================

Approval testing (a.k.a. golden-master / snapshot testing) reframes "is this
output still correct?" as "does it still match the version a human approved?".
:func:`verify_artifact` compares produced content to a stored
``<name>.approved.<ext>`` baseline:

* **match** → the check passes;
* **mismatch or missing baseline** → the produced bytes are written to
  ``<name>.received.<ext>`` and the check fails, so a reviewer can diff the two
  and, if the change is intended, promote it with :func:`approve_artifact`.

It works for *any* artifact — rendered text, JSON, OCR output, screenshot bytes
— so it complements pixel diffing with a review-gated baseline you commit
alongside the test. Pure standard library; imports no ``PySide6``. Names are
validated against path traversal.

Headless API
------------

.. code-block:: python

    from je_auto_control import verify_artifact, approve_artifact

    result = verify_artifact("invoice_render", produced_text,
                             approvals_dir="tests/.approvals")
    if not result.match:
        # first run is "new", a changed output is "mismatch"; review the
        # .received file, then bless it:
        approve_artifact("invoice_render", approvals_dir="tests/.approvals")

``content`` may be ``str`` or ``bytes`` (pass ``extension="png"`` for binary
snapshots). A verified run clears any stale received file.
``pending_artifacts(dir)`` lists names still awaiting approval. ``ApprovalResult``
carries ``status`` (``verified`` / ``mismatch`` / ``new``), ``match``, and both
file paths.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_verify_artifact``           Compare ``content`` to the approved baseline.
``AC_approve_artifact``          Promote the received artifact to the baseline.
``AC_pending_artifacts``         List artifacts awaiting approval.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_verify_artifact`` /
``ac_approve_artifact`` / ``ac_pending_artifacts``) and as Script Builder
commands under **Testing**.
