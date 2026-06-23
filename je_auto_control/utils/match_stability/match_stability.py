"""Pre-match settle gating and match persistence over a sequence of frames.

Matching mid-animation is a top flakiness source: the spinner is still spinning, a transition
is half-done, and the matcher fires on a transient. ``smart_waits.wait_until_screen_stable``
gates a *live polling loop* and returns a boolean — it cannot score stability on an *injectable*
sequence of frames, nor tell you whether a *match* held steady across them. ``match_stability``
adds both, on injected frames so it is unit-testable: ``region_stability`` scores how settled a
frame sequence is (consecutive-frame SSIM), and ``match_persistence`` checks that a template's
hit holds at the same place across the frames (low jitter), not just in one lucky frame.

Reuses ``ssim.ssim_compare``, ``visual_match.match_template`` and
``grounding_consensus.consensus_point``; no new matching code. The frames are injectable
(ndarray / path / PIL); OpenCV + NumPy arrive lazily via those modules. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence

ImageSource = Any


def region_stability(frames: Sequence[ImageSource], *,
                     settle_threshold: float = 0.99) -> Dict[str, Any]:
    """Score how settled a frame sequence is via consecutive-frame SSIM.

    Returns ``{stable, mean_ssim, min_ssim}`` — ``stable`` is true when the lowest
    consecutive-frame SSIM is at least ``settle_threshold`` (nothing moved between frames).
    A sequence shorter than two frames is trivially stable.
    """
    from je_auto_control.utils.ssim import ssim_compare
    frame_list = list(frames)
    if len(frame_list) < 2:
        return {"stable": True, "mean_ssim": 1.0, "min_ssim": 1.0}
    scores = [ssim_compare(frame_list[i], frame_list[i + 1])
              for i in range(len(frame_list) - 1)]
    lowest = min(scores)
    return {"stable": lowest >= float(settle_threshold),
            "mean_ssim": round(sum(scores) / len(scores), 4),
            "min_ssim": round(lowest, 4)}


def match_persistence(template: ImageSource, frames: Sequence[ImageSource], *,
                      min_score: float = 0.8, agree_px: float = 8) -> Dict[str, Any]:
    """Check that ``template`` matches the same place across ``frames``.

    Returns ``{persisted, n_hits, jitter}`` — ``persisted`` is true when the template is
    found in *every* frame and the hit centres agree (cluster within ``agree_px``);
    ``jitter`` is the spread of the agreeing centres (0 = rock steady).
    """
    from je_auto_control.utils.grounding_consensus import consensus_point
    from je_auto_control.utils.visual_match import match_template
    frame_list = list(frames)
    centers: List[List[int]] = []
    for frame in frame_list:
        match = match_template(template, haystack=frame, min_score=float(min_score))
        if match is not None:
            centers.append(match.center)
    if not centers:
        return {"persisted": False, "n_hits": 0, "jitter": None}
    result = consensus_point(centers, cluster_radius=float(agree_px))
    jitter: Optional[float] = result.spread if result else None
    persisted = (len(centers) == len(frame_list) and result is not None
                 and result.agreement >= 0.9)
    return {"persisted": persisted, "n_hits": len(centers), "jitter": jitter}
