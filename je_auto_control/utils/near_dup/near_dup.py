"""Near-duplicate text detection via SimHash and MinHash fingerprints.

``fuzzy.fuzzy_dedupe`` is O(n²) pairwise ``SequenceMatcher`` with no stable
fingerprint, and ``image_dedup`` only hashes pixels. This adds text
fingerprints — SimHash (Hamming-distance near-dup) and MinHash (estimated
Jaccard) — that scale and give a reusable signature, the text analog of the
perceptual image hash.

Pure standard library (``hashlib`` / ``re``); imports no ``PySide6``. A fixed
hash (``blake2b``, not the salted built-in ``hash()``) keeps fingerprints
deterministic across runs and CI.
"""
import hashlib
import re
from typing import List, Sequence

_TOKEN_RE = re.compile(r"\w+")


def _tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _shingles(text: str, k: int = 2) -> List[str]:
    tokens = _tokens(text)
    if len(tokens) < k:
        return [" ".join(tokens)] if tokens else [""]
    return [" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)]


def _hash64(value: str, salt: bytes = b"") -> int:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8,
                             salt=salt).digest()
    return int.from_bytes(digest, "big")


def simhash(text: str, *, bits: int = 64) -> int:
    """Return a ``bits``-wide SimHash fingerprint of ``text``."""
    vector = [0] * bits
    for shingle in _shingles(text):
        value = _hash64(shingle)
        for index in range(bits):
            vector[index] += 1 if (value >> index) & 1 else -1
    result = 0
    for index in range(bits):
        if vector[index] > 0:
            result |= (1 << index)
    return result


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two fingerprints."""
    return bin(a ^ b).count("1")


def near_duplicates(texts: Sequence[str], *, max_distance: int = 3,
                    bits: int = 64) -> List[List[int]]:
    """Cluster ``texts`` whose SimHashes are within ``max_distance`` bits.

    Returns a list of clusters, each a list of indices into ``texts``
    (singletons included, so the result partitions every input).
    """
    hashes = [simhash(text, bits=bits) for text in texts]
    assigned = [False] * len(texts)
    clusters: List[List[int]] = []
    for i in range(len(texts)):
        if assigned[i]:
            continue
        group = [i]
        assigned[i] = True
        for j in range(i + 1, len(texts)):
            if not assigned[j] and hamming_distance(hashes[i],
                                                    hashes[j]) <= max_distance:
                group.append(j)
                assigned[j] = True
        clusters.append(group)
    return clusters


def minhash_signature(text: str, *, num_perm: int = 64) -> List[int]:
    """Return a MinHash signature (``num_perm`` minima) of ``text``."""
    shingles = set(_shingles(text))
    signature: List[int] = []
    for seed in range(num_perm):
        salt = seed.to_bytes(2, "big")
        signature.append(min(_hash64(shingle, salt) for shingle in shingles))
    return signature


def minhash_similarity(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    """Estimate the Jaccard similarity from two MinHash signatures."""
    if not sig_a or len(sig_a) != len(sig_b):
        return 0.0
    equal = sum(1 for left, right in zip(sig_a, sig_b) if left == right)
    return equal / len(sig_a)
