"""Rebuild deterministic synthetic comparison PNGs without device access."""
from pathlib import Path
from random import Random

from PIL import Image


def build(destination: Path) -> None:
    """Write two template revisions, two target frames and an expected-miss frame."""
    destination.mkdir(parents=True, exist_ok=True)
    for version, seed in (("old", 41), ("new", 42)):
        with Image.frombytes("RGB", (17, 13), Random(seed).randbytes(17 * 13 * 3)) as template:
            template.save(destination / f"{version}.png")
            with Image.new("RGB", (64, 48), (240, 240, 240)) as frame:
                frame.paste(template, (20, 16))
                frame.save(destination / f"frame_{version}.png")
    with Image.new("RGB", (64, 48), (240, 240, 240)) as frame:
        frame.save(destination / "absent.png")


if __name__ == "__main__":
    build(Path(__file__).parent / "fixtures")
