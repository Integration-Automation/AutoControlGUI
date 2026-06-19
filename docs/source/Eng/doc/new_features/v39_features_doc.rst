Video Step-Overlay Report
=========================

A run already produces per-step screenshots; :func:`write_step_video` turns them
into a shareable walkthrough video where each step's frame is held for a few
seconds with its caption — and a pass/fail colour banner — burned in. It is the
visual companion to the HTML/JSON reports: a reviewer watches what the automation
did, step by step.

The orchestration (which frames, how many repeats per step, which caption) is
separated from OpenCV: the ``loader``, ``drawer``, and ``writer_factory`` hooks
are injectable, so the assembly logic is unit-testable with fakes and **no**
``cv2`` / ``numpy`` dependency. The real path lazily imports ``cv2`` only when
those hooks are not supplied. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import VideoStep, write_step_video

    steps = [
        VideoStep("step1.png", caption="Open the app", status="ok"),
        VideoStep("step2.png", caption="Submit the form", status="error"),
    ]
    result = write_step_video(steps, "walkthrough.mp4",
                              fps=10, seconds_per_step=2.5)
    print(result)   # {output, steps, fps, frame_count}

A step's ``image`` may be a file path (read with ``cv2.imread``) or an in-memory
frame. ``status`` of ``ok`` / ``error`` colours the caption banner green / red.
``build_overlay_plan(steps, fps, seconds_per_step)`` returns the per-step frame
plan without any I/O, and ``render_overlay_frame(frame, caption, status)`` burns a
single banner — both useful on their own.

Executor command
----------------

``AC_write_step_video`` takes ``steps`` (a list of ``{image, caption, status}``,
or a JSON string from the visual builder), an ``output`` path, and optional
``fps`` / ``seconds_per_step``; it returns ``{output, steps, fps, frame_count}``.
The same operation is exposed as the MCP tool ``ac_write_step_video`` and as a
Script Builder command under **Report**.
