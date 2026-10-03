"""Rebuild deterministic synthetic fixtures; no desktop or model access."""
import json
import random
from pathlib import Path

from PIL import Image


def pattern(seed: int, size: tuple[int, int]) -> Image.Image:
    """Create nonconstant RGB test pixels without external source material."""
    image = Image.new('RGB', size)
    for y in range(size[1]):
        for x in range(size[0]):
            image.putpixel((x, y), ((x * seed + y * 17) % 256, (y * seed + x * 11) % 256,
                                   (x * 23 + y * seed) % 256))
    return image


def main() -> None:
    """Write the versioned template-change and coordinate fixture dataset."""
    root = Path(__file__).resolve().parent
    pattern(31, (4, 4)).save(root / 'before.png')
    candidate = pattern(71, (4, 4))
    candidate.save(root / 'after.png')
    randomizer = random.Random(13)
    background = Image.frombytes('RGB', (24, 16), bytes(randomizer.randrange(256) for _ in range(24 * 16 * 3)))
    frame = background.copy()
    frame.paste(candidate, (4, 2))
    frame.save(root / 'target.png')
    background.save(root / 'negative.png')
    rows = [
        {'sample_id': 'changed-template', 'frame_path': 'target.png', 'expected_box': [4, 2, 4, 4]},
        {'sample_id': 'negative-origin', 'frame_path': 'target.png', 'expected_box': [-16, -8, 4, 4],
         'origin': [-20, -10]},
        {'sample_id': 'scaled-origin', 'frame_path': 'target.png', 'expected_box': [-18, -9, 2, 2],
         'origin': [-20, -10], 'scale': [2, 2]},
        {'sample_id': 'expected-miss', 'frame_path': 'negative.png', 'expected_miss': True},
        {'sample_id': 'unlabelled', 'frame_path': 'target.png'},
    ]
    (root / 'dataset.json').write_text(json.dumps({'schema_version': 1, 'samples': rows}, indent=2) + '\n',
                                     encoding='utf-8')


if __name__ == '__main__':
    main()
