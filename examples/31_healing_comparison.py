"""Compare fixed-frame strategies locally or evaluate an explicit labelled dataset."""
# pylint: disable=invalid-name  # reason: numbered example filenames follow the repository catalog
import argparse
import json
from dataclasses import dataclass

import je_auto_control as ac


@dataclass(frozen=True)
class FixedPrediction:
    """Controlled strategy used solely to demonstrate scoring on supplied bytes."""
    point: tuple[float, float]

    def locate(self, sample: ac.EvaluationSample) -> ac.LocatorPrediction:
        """Return the fixture prediction without capturing another frame."""
        return ac.LocatorPrediction(self.point if sample.frame else None, 'image')


def main() -> None:
    """Keep validation independent of image SDKs and external model APIs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--dataset')
    parser.add_argument('--versions', help='Version configuration JSON path')
    args = parser.parse_args()
    if bool(args.dataset) != bool(args.versions) or (args.validate and args.dataset):
        parser.error('--dataset and --versions must be paired, without --validate')
    if args.dataset:
        result = ac.compare_healing_versions(args.dataset, args.versions)
    else:
        sample = ac.EvaluationSample(b'controlled-fixed-frame', expected_box=(2, 2, 4, 4), sample_id='button')
        result = ac.evaluate_locators(
            [sample], {'v1': FixedPrediction((3, 3)), 'v2': FixedPrediction((9, 9))}).to_dict()
    print(json.dumps({'validated': True, 'comparison': result, 'native_operations': [],
                      'note': 'Location accuracy does not prove operation success.'}))


if __name__ == '__main__':
    main()
