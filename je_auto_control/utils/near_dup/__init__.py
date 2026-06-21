"""Near-duplicate text detection (SimHash / MinHash) for AutoControl."""
from je_auto_control.utils.near_dup.near_dup import (
    hamming_distance, minhash_signature, minhash_similarity, near_duplicates,
    simhash,
)

__all__ = [
    "hamming_distance", "minhash_signature", "minhash_similarity",
    "near_duplicates", "simhash",
]
