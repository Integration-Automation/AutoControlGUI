"""Perceptual hashing to dedupe near-identical screenshots / frames.

A screen recording or a step report often contains many nearly identical frames.
Perceptual hashes (average-hash and difference-hash) map visually similar images
to numerically close fingerprints, so they can be clustered by Hamming distance
and collapsed — keeping one representative per distinct view.

The hashing functions use **Pillow** (already a core dependency — no extra
package required); the dedupe/compare logic is pure Python and the ``hasher`` is
injectable, so clustering is unit-testable without any image. Imports no
``PySide6``.
"""
from typing import Any, Callable, List, Optional, Sequence


def _gray_resized(image: Any, size: tuple) -> Any:
    from PIL import Image
    img = image if hasattr(image, "convert") else Image.open(image)
    return img.convert("L").resize(size)


def _bits_to_hex(bits: str) -> str:
    width = (len(bits) + 3) // 4
    return f"{int(bits, 2):0{width}x}" if bits else "0"


def average_hash(image: Any, hash_size: int = 8) -> str:
    """Average-hash an image to a hex fingerprint (brightness vs. the mean)."""
    pixels = list(_gray_resized(image, (hash_size, hash_size)).getdata())
    average = sum(pixels) / len(pixels)
    return _bits_to_hex("".join("1" if p > average else "0" for p in pixels))


def dhash(image: Any, hash_size: int = 8) -> str:
    """Difference-hash an image (each pixel brighter than its right neighbour)."""
    width = hash_size + 1
    pixels = list(_gray_resized(image, (width, hash_size)).getdata())
    bits = [
        "1" if pixels[row * width + col] > pixels[row * width + col + 1]
        else "0"
        for row in range(hash_size) for col in range(hash_size)
    ]
    return _bits_to_hex("".join(bits))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Number of differing bits between two hex fingerprints."""
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def images_similar(hash_a: str, hash_b: str, max_distance: int = 5) -> bool:
    """Whether two fingerprints are within ``max_distance`` bits."""
    return hamming_distance(hash_a, hash_b) <= max_distance


def dedupe_images(images: Sequence[Any], *, max_distance: int = 5,
                  hasher: Optional[Callable[[Any], str]] = None) -> List[Any]:
    """Keep one image per near-duplicate cluster (first wins).

    Each image is dropped when its hash is within ``max_distance`` bits of an
    already-kept image. ``hasher`` defaults to :func:`average_hash`; inject a
    fake to test the clustering without real images.
    """
    compute = hasher or average_hash
    kept: List[Any] = []
    kept_hashes: List[str] = []
    for image in images:
        fingerprint = compute(image)
        if any(hamming_distance(fingerprint, seen) <= max_distance
               for seen in kept_hashes):
            continue
        kept.append(image)
        kept_hashes.append(fingerprint)
    return kept
