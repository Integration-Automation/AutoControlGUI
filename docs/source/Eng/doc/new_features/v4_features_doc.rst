===============================================
New Features (2026-06-17) — Automation Toolkit
===============================================

Thirty-plus automation primitives spanning input realism, vision, flow
control, triggers, window management, and file security — plus
recoverable (recycle-bin) deletion and a Recording-Editor undo. Every
feature ships with a headless Python API, an ``AC_*`` executor command,
and a visual Script Builder entry. Vision and window features keep their
geometry / IO operations injectable, so the logic is fully unit-tested
without a real screen or window.

.. contents::
   :local:
   :depth: 2


Human-like input
================

Move the cursor and type the way a person would — useful for demos,
realistic automation, and apps that watch for robotic timing. The path
and delay generators are pure and deterministic given a ``seed``::

    from je_auto_control import move_mouse_humanized, type_text_humanized

    # Curved, eased Bezier path with overshoot + jitter.
    move_mouse_humanized(800, 400, duration_s=0.5,
                         motion=None, seed=None)

    # Character-by-character typing with a jittered per-key delay.
    type_text_humanized("Hello, world", base_delay=0.05,
                        jitter=0.04, pause_chance=0.1, seed=1)

Executor commands: ``AC_human_move``, ``AC_human_type``.


Vision
======

* **VLM natural-language assertion** — ``assert_by_description("a green
  success toast")`` asks a vision-language model whether the screen
  matches a description (the ``verify()`` companion to
  ``locate_by_description``). ``AC_assert_vlm``.
* **Scroll-to-find** — ``scroll_until_visible(target, kind="image",
  direction="down", max_scrolls=10)`` scrolls until a template image or
  OCR text appears, returning ``{found, coords, scrolls}``.
  ``AC_scroll_to_find``.
* **Region colour stats** — ``region_color_stats(source, region)`` returns
  a region's ``average_rgb``, ``dominant_rgb``, and that colour's pixel
  fraction (quantise colour space → busiest bucket → average its real
  pixels). ``AC_region_color_stats``.
* **QR reading** — ``read_qr_codes(source, region)`` decodes QR codes via
  OpenCV's ``QRCodeDetector`` (no new dependency). ``AC_read_qr``.


Flow control & variables
========================

* **Reusable macros** — ``AC_define_macro`` registers a named,
  parameterised action sub-routine; ``AC_call_macro`` invokes it with
  ``${arg}`` bindings — the callable function the loop / if primitives
  couldn't express.
* **In-process parallel** — ``AC_parallel`` runs branch action lists
  concurrently, each on a fresh isolated executor so branches never race
  on shared variables (the in-process complement to the cross-host DAG).
* **Performance-budget assertion** — ``assert_duration(action, max_ms)``
  / ``AC_assert_duration`` fails a block that takes longer than the
  budget — a latency-regression guard bridging the profiler and the
  assertion DSL.
* **Read into a variable** — bind external data into the flow scope for
  later ``${var}`` use: ``AC_ocr_to_var`` (region text), ``AC_shell_to_var``
  (command stdout), ``AC_read_file_to_var`` (file text), ``AC_http_to_var``
  (GET body or a dotted JSON path), ``AC_now_to_var`` (strftime), and
  ``AC_random_to_var`` (seeded int / float / choice).
* **Transform a variable** — ``AC_transform_var`` applies upper / lower /
  strip / title / replace / regex-extract / slice, in place or into a new
  variable — pairs with the read-into-a-variable commands to clean raw
  text before use.
* **Assert a variable** — ``assert_variable(value, op, expected)`` /
  ``AC_assert_var`` fails when a variable doesn't satisfy
  eq / ne / lt / gt / contains / regex (the assertion-DSL companion to the
  branching ``if_var``).


Triggers & smart waits
======================

* **Composite triggers** — ``AllOfTrigger`` / ``AnyOfTrigger`` /
  ``SequenceTrigger`` combine any existing trigger by boolean AND, OR, or
  ordered sequence; the children reuse each trigger's ``is_fired()`` so
  any type nests freely.
* **Cron trigger** — ``CronTrigger("0 9 * * *")`` fires on a five-field
  cron expression, at most once per matching minute, and composes with
  the boolean triggers (e.g. *at 09:00 and only if the image is visible*).
* **More smart waits** — ``wait_until_clipboard_changes`` (changed / equals
  / contains, ``AC_wait_clipboard_change``) and ``wait_until_window_closed``
  (``AC_wait_window_closed``) round out the screen / pixel / region waits.


Window management
=================

* **Per-window capture** — ``capture_window(title, output_path)``
  resolves a window's geometry by title (Win32 ``GetWindowRect``) and
  screenshots exactly its bounds. ``AC_capture_window``.
* **Layout save / restore** — ``save_window_layout(path)`` snapshots every
  window's position to JSON; ``restore_window_layout(path)`` moves them all
  back (handy for test setup / teardown). ``AC_save_window_layout`` /
  ``AC_restore_window_layout``.
* **Snap / tile** — ``snap_window(title, "left")`` moves a window to a
  screen half (left / right / top / bottom), a quarter (the four corners),
  or ``"max"``. ``AC_snap_window``.


File security & safety
======================

* **Action-file signing** — ``sign_action_file`` writes an HMAC-SHA256
  ``.sig`` sidecar; ``verify_action_file`` checks it in constant time.
  ``execute_files`` enforces signatures when
  ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` is set (opt-in).
  ``AC_sign_action_file`` / ``AC_verify_action_file``.
* **Action-file encryption** — ``encrypt_action_file`` /
  ``decrypt_action_file`` keep a script's contents secret at rest with
  Fernet (AES-128-CBC + HMAC), keyed by a passphrase or a per-user 0600
  key. ``AC_encrypt_action_file`` / ``AC_decrypt_action_file``.
* **Recoverable deletion** — ``move_to_trash(path)`` sends a file to the OS
  recycle bin (Win32 ``SHFileOperation`` undo flag / macOS Trash / Linux
  XDG trash, preferring ``send2trash``) so a "deleted" file can be
  restored. ``AC_move_to_trash``.


Reporting & notifications
=========================

* **Screenshot annotation** — ``annotate_screenshot(source, annotations,
  output_path)`` draws labelled boxes, translucent highlights, arrows, and
  text onto a capture (the marking complement to redaction's blurring).
  ``AC_annotate_screenshot``.
* **Desktop notifications** — ``notify(title, message)`` shows a
  cross-platform toast (``notify-send`` / ``osascript`` / PowerShell);
  injection-safe (Linux argv, macOS / Windows a static script reading the
  strings from environment variables). ``AC_notify``.


GUI
===

* **Recording Editor undo** — every edit (remove step, trim, rescale,
  adjust delays, filter) is snapshotted onto an undo stack; **Ctrl+Z** and
  an Undo button restore the prior state.
* **Triggers tab** — *Combine selected* wraps chosen triggers into an
  AllOf / AnyOf / Sequence composite; a new **Cron** trigger type.
* **Assertions tab** — a new **VLM** ("screen matches description")
  assertion kind.
* Every new ``AC_*`` command is buildable in the visual **Script Builder**.
