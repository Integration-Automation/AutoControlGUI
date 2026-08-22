"""ORB feature matching: locate a template that is rotated, rescaled or re-themed.

Template matching (``match_template`` / ``match_masked``) correlates pixels, so it
fails the moment the target is rotated, scaled by a non-listed factor, or its
colours change (light vs dark theme, hover state). ORB matches *keypoints* —
distinctive corners described by orientation-invariant binary descriptors — and
fits a homography through them, so it finds the element under rotation, scale and
appearance change, and reports the four projected corners plus the inlier count
as a confidence signal.

It runs on an injectable ``haystack`` image (ndarray / path / PIL), so it is
unit-testable on synthetic arrays without a real screen. OpenCV + NumPy come in
via the project's ``je_open_cv`` dependency and are imported lazily. Imports no
``PySide6``. ORB, the brute-force matcher and ``findHomography`` are all in core
OpenCV (no contrib modules).
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import (
    _haystack_gray, _to_gray,
)

ImageSource = Any


@dataclass(frozen=True)
class FeatureMatch:
    """A homography-located match: projected corners, centre, inliers, score."""

    corners: List[List[int]]
    center: List[int]
    inliers: int
    matches: int
    score: float

    def to_dict(self) -> Dict[str, Any]:
        """Return the match as a plain dict."""
        return asdict(self)


def _ratio_filter(knn_matches, ratio: float) -> list:
    """Lowe's ratio test: keep matches clearly better than their runner-up."""
    good = []
    for pair in knn_matches:
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance:
            good.append(pair[0])
    return good


def _make_orb(template_gray, max_features: int):
    """Build an ORB detector with border/patch sizes that suit small templates.

    OpenCV's default ``edgeThreshold``/``patchSize`` (31) reject every keypoint
    in an icon-sized template, so they are scaled down to the template.
    """
    import cv2
    smaller = min(template_gray.shape[:2])
    patch = max(7, min(31, smaller // 3))
    edge = max(2, patch // 3)
    return cv2.ORB_create(# type: ignore[attr-defined]  # reason: absent from the cv2 stub
        nfeatures=int(max_features), edgeThreshold=edge,
        patchSize=patch)


def _keypoint_matches(template_gray, scene_gray, max_features: int, ratio: float):
    """Return (kp_template, kp_scene, good_matches) or None if too few features."""
    import cv2
    orb = _make_orb(template_gray, max_features)
    kp1, des1 = orb.detectAndCompute(template_gray, None)
    kp2, des2 = orb.detectAndCompute(scene_gray, None)
    if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    good = _ratio_filter(matcher.knnMatch(des1, des2, k=2), float(ratio))
    return kp1, kp2, good


def _locate(template_shape, kp1, kp2, good, min_inliers: int
            ) -> Optional[FeatureMatch]:
    """Fit a RANSAC homography from ``good`` matches and project the template box."""
    import cv2
    import numpy as np
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if homography is None:
        return None
    inliers = int(mask.sum())
    if inliers < int(min_inliers):
        return None
    height, width = template_shape[:2]
    box = np.float32([[0, 0], [width, 0], [width, height],
                      [0, height]]).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(box, homography).reshape(-1, 2)
    corners = [[int(round(px)), int(round(py))] for px, py in projected]
    center = [int(round(float(projected[:, 0].mean()))),
              int(round(float(projected[:, 1].mean())))]
    return FeatureMatch(corners, center, inliers, len(good),
                        round(inliers / len(good), 4))


def feature_match(template: ImageSource, *,
                  haystack: Optional[ImageSource] = None,
                  region: Optional[Sequence[int]] = None,
                  max_features: int = 500, ratio: float = 0.75,
                  min_inliers: int = 10) -> Optional[FeatureMatch]:
    """Locate ``template`` in the scene by ORB keypoints + a RANSAC homography.

    Robust to rotation, scale and appearance change. ``haystack`` is an ndarray /
    path / PIL image (default: grab the screen / ``region``). ``ratio`` is Lowe's
    ratio-test cutoff; at least ``min_inliers`` geometrically consistent matches
    are required. Returns a :class:`FeatureMatch` (projected ``corners``,
    ``center``, ``inliers``, ``score``) or ``None`` when the target is not found.
    """
    template_gray = _to_gray(template)
    scene_gray = _haystack_gray(haystack, region)
    found = _keypoint_matches(template_gray, scene_gray, max_features, ratio)
    if found is None:
        return None
    kp1, kp2, good = found
    if len(good) < int(min_inliers):
        return None
    return _locate(template_gray.shape, kp1, kp2, good, min_inliers)
