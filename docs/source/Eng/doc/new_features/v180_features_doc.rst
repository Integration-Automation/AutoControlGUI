Pre-Match Settle Gating + Match Persistence
===========================================

Matching mid-animation is a top flakiness source: the spinner is still spinning, a transition
is half-done, and the matcher fires on a transient. ``smart_waits.wait_until_screen_stable``
gates a *live polling loop* and returns a boolean — it cannot score stability on an *injectable*
sequence of frames, nor tell you whether a *match* held steady across them. ``match_stability``
adds both, on injected frames so it is unit-testable: ``region_stability`` scores how settled a
frame sequence is (consecutive-frame SSIM), and ``match_persistence`` checks that a template's
hit holds at the same place across the frames (low jitter), not just in one lucky frame.

It reuses ``ssim.ssim_compare``, ``visual_match.match_template`` and
``grounding_consensus.consensus_point`` — no new matching code. The frames are injectable
(ndarray / path / PIL). Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import region_stability, match_persistence

    frames = [grab(), grab(), grab()]   # a few snapshots of the same region
    if region_stability(frames, settle_threshold=0.99)["stable"]:
        do_the_match()

    result = match_persistence("button.png", frames, min_score=0.8, agree_px=8)
    if result["persisted"]:
        print("steady hit, jitter", result["jitter"])

``region_stability`` returns ``{stable, mean_ssim, min_ssim}`` — ``stable`` when the lowest
consecutive-frame SSIM clears ``settle_threshold``. ``match_persistence`` returns
``{persisted, n_hits, jitter}`` — ``persisted`` when the template is found in *every* frame and
the hit centres agree within ``agree_px`` (``jitter`` is their spread; 0 = rock steady).

Executor commands
-----------------

``AC_region_stability`` (``frames`` / ``settle_threshold`` → ``{stable, mean_ssim, min_ssim}``)
and ``AC_match_persistence`` (``template`` / ``frames`` / ``min_score`` / ``agree_px`` →
``{persisted, n_hits, jitter}``). They are exposed as the MCP tools ``ac_region_stability`` /
``ac_match_persistence`` (read-only) and as the Script Builder commands **Region Stability
(frames)** / **Match Persistence (frames)** under **Image**.
