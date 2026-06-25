Read and Control the System Volume
==================================

Unattended runs often need a known audio baseline — mute before a noisy batch,
restore a level afterwards, or assert the current volume — but the framework
only had the blind media-key steps (``volume up`` / ``down`` nudge by an unknown
amount with no read-back). ``system_volume`` adds absolute, read-backable
control of the default output device.

* :func:`get_volume` / :func:`set_volume` / :func:`change_volume` — read and
  write the master level as an integer percent ``0..100`` (``set_volume`` and
  ``change_volume`` clamp to that range).
* :func:`is_muted` / :func:`set_mute` / :func:`mute` / :func:`unmute` /
  :func:`toggle_mute` — read and write the mute flag.

All logic (clamping, percent <-> scalar conversion, toggle) is pure and runs
through an injectable :class:`VolumeDriver` seam, so it is fully testable without
an audio device. The default driver drives the Windows Core Audio
``IAudioEndpointVolume`` interface through the optional ``pycaw`` dependency
(``pip install je_auto_control[audio]``); on a platform / install without it the
default driver raises a clear error telling the caller to pass ``driver=``.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        get_volume, set_volume, change_volume, is_muted, mute, unmute,
        toggle_mute,
    )

    get_volume()            # e.g. 65 — current master volume percent
    set_volume(30)          # set to 30 %, returns 30
    change_volume(-10)      # lower by 10 %, returns the applied percent
    is_muted()              # False
    mute()                  # True  — silence the output
    unmute()                # False — restore it
    toggle_mute()           # flip and return the new state

For tests (or any non-Windows host) pass a ``driver`` — any object exposing
``get_scalar`` / ``set_scalar`` / ``get_mute`` / ``set_mute`` over a ``0.0..1.0``
scalar:

.. code-block:: python

    class FakeVolume:
        def __init__(self, scalar=0.5, muted=False):
            self.scalar, self.muted = scalar, muted
        def get_scalar(self): return self.scalar
        def set_scalar(self, s): self.scalar = s
        def get_mute(self): return self.muted
        def set_mute(self, m): self.muted = m

    drv = FakeVolume()
    set_volume(73, driver=drv)   # 73, drv.scalar == 0.73

Executor commands
-----------------

``AC_get_volume`` (→ ``{volume, muted}``), ``AC_set_volume`` (``level`` →
``{volume}``), ``AC_change_volume`` (``delta`` → ``{volume}``), ``AC_set_mute``
(``muted`` → ``{muted}``) and ``AC_toggle_mute`` (→ ``{muted}``). They are
exposed as the matching ``ac_*`` MCP tools (the read is read-only, the writes
side-effect-only) and as Script Builder commands under **Shell**. The executor
and MCP layers use the default OS driver, so they require ``pycaw`` on Windows.
