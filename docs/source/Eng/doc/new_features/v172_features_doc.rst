Grounding Self-Consistency (Consensus Over Proposals)
=====================================================

A target can be grounded several ways at once — set-of-marks, OCR, template match, the a11y
tree, or N samples from a model — and they don't always agree. ``ab_locator`` /
``element_scoring`` rank locator *strategies* by historical reliability but never fuse
*simultaneous* proposals into one consensus point with a dispersion metric, and
``action_grounding.snap_to_element`` snaps a *single* coordinate to the nearest element with no
notion of disagreement. ``grounding_consensus`` clusters the candidate points (or votes
candidate elements), returns the agreed target plus an *agreement* fraction and *spread*, and
flags low-agreement targets so the caller can zoom / ask a human instead of clicking blind.

Pure-stdlib geometry; deterministic and unit-testable with no device. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import consensus_point, consensus_element, is_confident

    proposals = [[480, 260], [484, 258], [477, 263], [900, 100]]  # one outlier
    result = consensus_point(proposals, cluster_radius=24)
    if is_confident(result, min_agreement=0.6):
        click(*result.point)
    else:
        print("proposals disagree:", result.agreement, result.spread)

    # or vote proposals onto a known element list
    element, agreement = consensus_element(proposals, elements)

``consensus_point`` clusters ``[x, y]`` or ``[x, y, weight]`` candidates and returns a
``ConsensusResult`` (``point`` / ``agreement`` — winning cluster weight over total / ``spread``
/ ``n_clusters``), or ``None`` when empty. ``consensus_element`` votes each proposal to its
nearest element and returns ``(element, agreement)``. ``is_confident`` thresholds the agreement.

Executor commands
-----------------

``AC_consensus_point`` (``candidates`` / ``cluster_radius`` → ``{found, result}``) and
``AC_consensus_element`` (``candidates`` / ``elements`` → ``{found, element, agreement}``). They
are exposed as the MCP tools ``ac_consensus_point`` / ``ac_consensus_element`` (read-only) and
as the Script Builder commands **Grounding Consensus Point** / **Grounding Consensus Element**
under **Native UI**.
