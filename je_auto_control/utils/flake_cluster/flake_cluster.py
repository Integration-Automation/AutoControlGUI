"""Cluster tests that flake *together* by co-failure similarity.

Flaky tests are rarely independent: a wobbly shared fixture, a slow dependency or
a noisy environment makes a *group* of tests fail in the same runs (research finds
~75% of flaky tests fall into co-failure clusters). Ranking tests one-by-one by
flip rate misses that shared root cause. ``flake_cluster`` measures how often each
pair of tests fails in the *same* runs (Jaccard similarity over the set of runs
each failed in) and groups tests whose co-failure exceeds a threshold into
clusters — so you can chase one root cause instead of N symptoms.

Input is a list of runs, each a collection of the test names that failed in that
run. Pure standard library; no device, no ``PySide6``.
"""
from itertools import combinations
from typing import Any, Dict, List, Sequence, Set


def _set_jaccard(left: Set[int], right: Set[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _fail_runs(runs: Sequence[Sequence[str]]) -> Dict[str, Set[int]]:
    """Map each test name to the set of run indices in which it failed."""
    fails: Dict[str, Set[int]] = {}
    for index, run in enumerate(runs):
        for test in set(run):
            fails.setdefault(str(test), set()).add(index)
    return fails


def cofailure_pairs(runs: Sequence[Sequence[str]], *,
                    threshold: float = 0.5) -> List[Dict[str, Any]]:
    """Return test pairs whose co-failure Jaccard meets ``threshold``.

    Each entry is ``{tests:[a,b], jaccard, co_failures}``, most similar first.
    """
    fails = _fail_runs(runs)
    pairs = []
    for left, right in combinations(sorted(fails), 2):
        score = _set_jaccard(fails[left], fails[right])
        if score >= float(threshold):
            pairs.append({"tests": [left, right], "jaccard": round(score, 3),
                          "co_failures": len(fails[left] & fails[right])})
    pairs.sort(key=lambda pair: pair["jaccard"], reverse=True)
    return pairs


def _connected_components(nodes: Sequence[str],
                          adjacency: Dict[str, Set[str]]) -> List[List[str]]:
    seen: Set[str] = set()
    components = []
    for node in nodes:
        if node in seen:
            continue
        stack, component = [node], []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(adjacency[current] - seen)
        components.append(component)
    return components


def _cohesion(component: Sequence[str], fails: Dict[str, Set[int]]) -> float:
    scores = [_set_jaccard(fails[a], fails[b])
              for a, b in combinations(component, 2)]
    return round(sum(scores) / len(scores), 3) if scores else 1.0


def failure_clusters(runs: Sequence[Sequence[str]], *, threshold: float = 0.5,
                     min_size: int = 2) -> List[Dict[str, Any]]:
    """Group tests that fail together into co-failure clusters.

    Builds a graph linking test pairs whose co-failure Jaccard meets
    ``threshold``, then returns its connected components of at least ``min_size``
    tests as ``[{tests, size, cohesion}]`` (largest / most cohesive first).
    ``cohesion`` is the mean pairwise Jaccard within the cluster.
    """
    fails = _fail_runs(runs)
    tests = sorted(fails)
    adjacency: Dict[str, Set[str]] = {test: set() for test in tests}
    for left, right in combinations(tests, 2):
        if _set_jaccard(fails[left], fails[right]) >= float(threshold):
            adjacency[left].add(right)
            adjacency[right].add(left)
    clusters = []
    for component in _connected_components(tests, adjacency):
        if len(component) >= int(min_size):
            clusters.append({"tests": sorted(component), "size": len(component),
                             "cohesion": _cohesion(component, fails)})
    clusters.sort(key=lambda cluster: (cluster["size"], cluster["cohesion"]),
                  reverse=True)
    return clusters
