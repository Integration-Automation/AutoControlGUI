"""Fixed-frame evaluation distinguishes labelled recovery from guesses."""
import hashlib
import io

import pytest

from je_auto_control.utils.self_healing import locator
from je_auto_control.utils.self_healing.heal_log import HealEventLog


class FakeStrategy:
    def __init__(self, coordinates, method='image'):
        self.coordinates = coordinates
        self.method = method
        self.seen = []

    def locate(self, sample):
        from je_auto_control.utils.self_healing.evaluation import LocatorPrediction
        self.seen.append(sample)
        return LocatorPrediction(self.coordinates.get(sample.sample_id), self.method)


def sample(identifier, expected_box=None, **kwargs):
    from je_auto_control.utils.self_healing.evaluation import EvaluationSample
    return EvaluationSample(frame=b'fixed-frame-' + identifier.encode(), sample_id=identifier,
                            expected_box=expected_box, **kwargs)


def compare(samples, strategies):
    from je_auto_control.utils.self_healing.evaluation import evaluate_locators
    return evaluate_locators(samples, strategies)


def test_unlabelled_is_unknown():
    result = compare([sample('unknown')], {'v1': FakeStrategy({'unknown': (3, 3)})})
    report = result.versions['v1']
    assert report.unknown == 1
    assert report.correct == 0
    assert report.accuracy.denominator == 0 and report.accuracy.value is None


def test_false_positive_is_not_recovery():
    samples = [sample('correct', (2, 2, 4, 4)), sample('wrong', (2, 2, 4, 4))]
    report = compare(samples, {'v1': FakeStrategy({'correct': (3, 3), 'wrong': (9, 9)}, 'vlm')}).versions['v1']
    assert report.correct == 1 and report.false_positive == 1
    assert report.recovery.numerator == 1 and report.recovery.denominator == 2
    assert report.operation_success.denominator == 0


def test_same_frame_versions_are_comparable():
    samples = [sample('shared', (0, 0, 8, 8))]
    before, after = FakeStrategy({'shared': None}), FakeStrategy({'shared': (4, 4)})
    result = compare(samples, {'before': before, 'after': after})
    assert before.seen[0].frame is after.seen[0].frame
    assert before.seen[0].frame == samples[0].frame
    assert result.versions['after'].trials[0].frame_hash == hashlib.sha256(samples[0].frame).hexdigest()
    assert result.versions['before'].miss == 1
    assert result.versions['after'].correct == 1


def test_region_passed_to_both_strategies(monkeypatch, tmp_path):
    regions = []

    def image(template_path, threshold, screen_region=None):
        regions.append(screen_region)
        return None, 'controlled miss'

    def vlm(description, screen_region, model):
        regions.append(screen_region)
        return (-15, 10), None

    monkeypatch.setattr(locator, '_try_image', image)
    monkeypatch.setattr(locator, '_try_vlm', vlm)
    outcome = locator.self_heal_locate('template.png', 'button', screen_region=[-20, 0, 20, 30],
                                       log=HealEventLog(tmp_path / 'heal.jsonl'))
    image_region, vlm_region = regions
    assert image_region == vlm_region == [-20, 0, 20, 30]
    assert outcome.coordinates == (-15, 10)


def test_scale_and_negative_origin_are_applied_once():
    samples = [sample('scaled', (-98, -48, 4, 4), origin=(-100, -50), scale=(2, 2))]
    report = compare(samples, {'v1': FakeStrategy({'scaled': (6, 8)})}).versions['v1']
    assert report.correct == 1
    assert report.trials[0].coordinates == (-97, -46)


def test_expected_miss_requires_a_real_miss():
    samples = [sample('negative', expected_miss=True)]
    result = compare(samples, {'miss': FakeStrategy({}), 'guess': FakeStrategy({'negative': (4, 4)}, 'vlm')})
    assert result.versions['miss'].correct == 1
    assert result.versions['guess'].false_positive == 1
    assert result.versions['guess'].recovery.denominator == 0


def test_strategy_failure_is_not_a_correct_expected_miss():
    class FailedStrategy:
        def locate(self, sample):
            raise RuntimeError('controlled failure')

    report = compare([sample('negative', expected_miss=True)], {'broken': FailedStrategy()}).versions['broken']
    assert report.correct == 0
    assert report.errors == 1
    assert report.p50_ms is not None and report.p95_ms is not None


@pytest.mark.parametrize('scale', [(0, 1), (float('nan'), 1), (-1, 1)])
def test_invalid_scale_is_rejected(scale):
    from je_auto_control.utils.self_healing.evaluation import HealingEvaluationError
    with pytest.raises(HealingEvaluationError):
        sample('invalid', scale=scale)


def _png(pattern, size=(12, 12)):
    from PIL import Image
    image = Image.new('RGB', size)
    for y in range(size[1]):
        for x in range(size[0]):
            image.putpixel((x, y), ((x * pattern + y * 17) % 256, (y * pattern + x * 11) % 256,
                                   (x * 23 + y * pattern) % 256))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


@pytest.fixture
def revision_fixture(tmp_path):
    from PIL import Image
    from je_auto_control.utils.self_healing.evaluation import EvaluationSample
    from je_auto_control.utils.self_healing.template_revisions import TemplateRevisionStore
    target, candidate = tmp_path / 'current.png', tmp_path / 'proposal.png'
    target.write_bytes(_png(31, (4, 4)))
    candidate.write_bytes(_png(71, (4, 4)))
    frame = Image.open(io.BytesIO(_png(13)))
    frame.paste(Image.open(candidate), (4, 4))
    stream = io.BytesIO()
    frame.save(stream, format='PNG')
    samples = [EvaluationSample(stream.getvalue(), expected_box=(4, 4, 4, 4), sample_id='positive')]
    store = TemplateRevisionStore(tmp_path / 'revisions')
    return store, target, candidate, samples


def test_candidate_preview_does_not_replace_the_current_template(revision_fixture):
    store, target, candidate, samples = revision_fixture
    original = target.read_bytes()
    identifier = store.propose(target, candidate)
    preview = store.preview(identifier)
    assert preview['status'] == 'candidate'
    assert preview['base_hash'] == hashlib.sha256(original).hexdigest()
    assert target.read_bytes() == original


def test_candidate_requires_validation_before_accept(revision_fixture):
    from je_auto_control.utils.self_healing.evaluation import HealingEvaluationError
    store, target, candidate, samples = revision_fixture
    identifier = store.propose(target, candidate)
    original = target.read_bytes()
    with pytest.raises(HealingEvaluationError, match='validat'):
        store.accept(identifier)
    assert target.read_bytes() == original


def test_candidate_can_be_validated_accepted_and_reverted(revision_fixture):
    store, target, candidate, samples = revision_fixture
    original = target.read_bytes()
    identifier = store.propose(target, candidate)
    comparison = store.validate(identifier, samples)
    assert comparison.versions['candidate'].correct == 1
    assert store.accept(identifier)['status'] == 'accepted'
    assert target.read_bytes() == candidate.read_bytes()
    assert store.revert(identifier)['status'] == 'reverted'
    assert target.read_bytes() == original


def test_accept_does_not_overwrite_a_concurrently_changed_template(revision_fixture):
    from je_auto_control.utils.self_healing.evaluation import HealingEvaluationError
    store, target, candidate, samples = revision_fixture
    identifier = store.propose(target, candidate)
    store.validate(identifier, samples)
    target.write_bytes(_png(41))
    external = target.read_bytes()
    with pytest.raises(HealingEvaluationError, match='changed'):
        store.accept(identifier)
    assert target.read_bytes() == external


def test_unknown_only_validation_cannot_authorize_accept(revision_fixture):
    from je_auto_control.utils.self_healing.evaluation import EvaluationSample, HealingEvaluationError
    store, target, candidate, samples = revision_fixture
    identifier = store.propose(target, candidate)
    store.validate(identifier, [EvaluationSample(samples[0].frame, sample_id='unknown')])
    with pytest.raises(HealingEvaluationError, match='validat'):
        store.accept(identifier)


def test_preview_of_missing_store_creates_no_files(tmp_path):
    from je_auto_control.utils.self_healing.template_revisions import TemplateRevisionStore
    from je_auto_control.utils.self_healing.evaluation import HealingEvaluationError
    location = tmp_path / 'absent-store'
    with pytest.raises(HealingEvaluationError):
        TemplateRevisionStore(location).preview('a' * 32)
    assert not location.exists()


def test_candidate_snapshot_tampering_is_rejected(revision_fixture):
    from pathlib import Path
    from je_auto_control.utils.self_healing.evaluation import HealingEvaluationError
    store, target, candidate, samples = revision_fixture
    identifier = store.propose(target, candidate)
    preview = store.preview(identifier)
    Path(preview['candidate_path']).write_bytes(_png(89))
    with pytest.raises(HealingEvaluationError, match='changed'):
        store.validate(identifier, samples)


def test_heal_log_reads_legacy_records_and_retains_new_context(tmp_path):
    import json
    from je_auto_control.utils.self_healing.heal_log import HealEvent
    path = tmp_path / 'heal.jsonl'
    path.write_text(json.dumps({'timestamp': 'old', 'method': 'image', 'coordinates': [1, 2],
                                'duration_ms': 1}) + '\n', encoding='utf-8')
    log = HealEventLog(path)
    log.append(HealEvent('new', 'vlm', [3, 4], 2, locator_version='v2',
                         context={'run_id': 'run', 'step_id': 'step', 'verified_success': None}))
    old, new = log.list_events()
    assert old.schema_version == 1
    assert new.schema_version == 2 and new.locator_version == 'v2'
    assert new.context['verified_success'] is None


def test_runtime_detection_does_not_claim_operation_verification(monkeypatch, tmp_path):
    from je_auto_control.utils.self_healing.healing_context import healing_context
    log = HealEventLog(tmp_path / 'runtime.jsonl')
    monkeypatch.setattr(locator, '_try_image', lambda *args: ((3, 4), None))
    with healing_context('version-two', locator_id='button'):
        locator.self_heal_locate('fixture.png', log=log)
    event = log.list_events()[0]
    assert event.locator_version == 'version-two'
    assert event.context['detection_found'] is True
    assert event.context['verified_success'] is None
    assert event.context['strategy_durations_ms']['image'] >= 0


def test_dataset_api_generates_the_same_report_without_capture(revision_fixture, tmp_path, monkeypatch):
    import json
    from je_auto_control.utils.self_healing.evaluation_api import compare_healing_versions
    from je_auto_control.utils.monitor_layout import logical_frame
    store, target, candidate, samples = revision_fixture
    (tmp_path / 'frame.png').write_bytes(samples[0].frame)
    dataset = tmp_path / 'dataset.json'
    dataset.write_text(json.dumps({'schema_version': 1, 'samples': [
        {'sample_id': 'positive', 'frame_path': 'frame.png', 'expected_box': [4, 4, 4, 4]}]}), encoding='utf-8')
    monkeypatch.setattr(logical_frame, 'grab_logical', lambda *args, **kwargs: pytest.fail('comparison recaptured'))
    report_path = tmp_path / 'report.json'
    report = compare_healing_versions(str(dataset), {'candidate': {'template_path': str(candidate)}},
                                      report_path=str(report_path))
    assert report['versions']['candidate']['correct'] == 1
    assert json.loads(report_path.read_text(encoding='utf-8')) == report
    assert report_path.with_suffix('.html').is_file()


def test_healing_evaluation_surfaces_are_complete():
    import je_auto_control as ac
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {'compare_healing_versions', 'create_template_candidate', 'preview_template_candidate',
             'validate_template_candidate', 'accept_template_candidate', 'revert_template_revision'}
    assert names <= set(ac.__all__)
    assert {'AC_' + name for name in names} <= set(Executor().known_commands())
    assert {'AC_' + name for name in names} <= set(COMMAND_SPECS)
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    assert {'ac_' + name for name in names} <= set(tools)
    assert tools['ac_preview_template_candidate'].annotations.read_only is True
    assert tools['ac_accept_template_candidate'].annotations.destructive is True


def test_failed_fallback_keeps_its_recovery_denominator():
    class FailedVLM:
        method = 'vlm'

        def locate(self, sample):
            raise RuntimeError('controlled model failure')

    report = compare([sample('positive', (0, 0, 5, 5))], {'v2': FailedVLM()}).versions['v2']
    assert report.fallback == 1
    assert report.recovery.numerator == 0 and report.recovery.denominator == 1


def test_report_retains_original_step_and_expected_geometry():
    from je_auto_control.utils.self_healing.evaluation import EvaluationSample
    item = EvaluationSample(b'fixed', expected_box=(1, 2, 4, 4), sample_id='observed-step',
                             context={'run_id': 'original-run', 'step_id': 'original-step'})
    report = compare([item], {'v2': FakeStrategy({'observed-step': (3, 4)})}).to_dict()
    evidence = report['versions']['v2']['trials'][0]['sample']
    assert evidence['context']['step_id'] == 'original-step'
    assert evidence['expected_box'] == [1, 2, 4, 4]


def test_historical_operation_verification_is_not_transferred_to_a_new_prediction():
    item = sample('original', (0, 0, 5, 5), operation_verified=True)
    report = compare([item], {'wrong': FakeStrategy({'original': (20, 20)}),
                              'new-hit': FakeStrategy({'original': (2, 2)})})
    assert all(version.operation_success.denominator == 0 for version in report.versions.values())


def test_fallback_recovers_after_an_image_backend_error():
    from je_auto_control.utils.self_healing.frame_strategies import FallbackFrameStrategy

    class FailedImage:
        def locate(self, item):
            raise RuntimeError('controlled image failure')

    strategy = FallbackFrameStrategy(FailedImage(), FakeStrategy({'positive': (2, 2)}, 'vlm'))
    report = compare([sample('positive', (0, 0, 5, 5))], {'fallback': strategy}).versions['fallback']
    assert report.correct == 1 and report.recovery.numerator == 1


def test_region_image_converts_ltrb_and_preserves_absolute_negative_coordinates(monkeypatch):
    from je_auto_control.utils.cv2_utils import template_detection
    regions = []

    def find(template, threshold, screen_region):
        regions.append(screen_region)
        return True, [-18, -8, -10, 0]

    monkeypatch.setattr(template_detection, 'find_image', find)
    assert locator._try_region_image('fixture.png', 0.9, [-20, -10, 20, 30]) == (-14, -4)
    assert regions == [[-20, -10, 40, 40]]


def test_versioned_fixed_dataset_covers_negative_scaled_and_changed_templates(tmp_path):
    from pathlib import Path
    from je_auto_control.utils.self_healing.evaluation_api import compare_healing_versions
    root = Path(__file__).resolve().parents[3] / 'benchmarks/self_healing'
    report = compare_healing_versions(str(root / 'dataset.json'), {
        'before': {'template_path': str(root / 'before.png'), 'threshold': 0.99},
        'after': {'template_path': str(root / 'after.png'), 'threshold': 0.99}},
        report_path=str(tmp_path / 'comparison.json'))
    assert report['sample_count'] == 5
    assert report['versions']['before']['accuracy'] == {'numerator': 1, 'denominator': 4, 'value': 0.25}
    assert report['versions']['after']['accuracy'] == {'numerator': 4, 'denominator': 4, 'value': 1.0}
    assert report['versions']['after']['unknown'] == 1
    assert report['versions']['after']['operation_success']['denominator'] == 0
    trials = report['versions']['after']['trials']
    assert trials[1]['coordinates'] == [-14, -6]
    assert trials[2]['coordinates'] == [-17, -8]


def test_runtime_image_event_keeps_actual_capture_identity(revision_fixture, monkeypatch, tmp_path):
    from PIL import Image
    from je_auto_control.utils.cv2_utils import template_detection
    store, target, candidate, samples = revision_fixture
    monkeypatch.setattr(template_detection, 'grab_logical',
                        lambda *args, **kwargs: (Image.open(io.BytesIO(samples[0].frame)), -20, -10))
    log = HealEventLog(tmp_path / 'capture.jsonl')
    outcome = locator.self_heal_locate(str(candidate), log=log)
    event = log.list_events()[0]
    assert outcome.coordinates == (-14, -4)
    assert isinstance(event.context['frame_hash'], str) and len(event.context['frame_hash']) == 64
    assert event.context['backend'] == 'opencv'
    assert event.context['candidate_coordinates'] == [-14, -4]


def test_runtime_vlm_event_keeps_backend_model_and_frame(monkeypatch, tmp_path):
    from je_auto_control.utils.vision import vlm_api

    class Backend:
        available, name = True, 'controlled-vlm'

        def locate(self, frame, description, model):
            return (2, 3)

    monkeypatch.setattr(vlm_api, 'get_backend', lambda: Backend())
    content = _png(13)
    monkeypatch.setattr(vlm_api, '_capture_screenshot_bytes', lambda region: content)
    log = HealEventLog(tmp_path / 'vlm.jsonl')
    locator.self_heal_locate(description='controlled target', model='fixture-model', log=log)
    event = log.list_events()[0]
    assert event.context['frame_hash'] == hashlib.sha256(content).hexdigest()
    assert event.context['backend'] == 'controlled-vlm' and event.context['model'] == 'fixture-model'
    assert event.context['cost'] is None


def test_heal_log_rejects_future_schema_and_non_json_context(tmp_path):
    import json
    from je_auto_control.utils.self_healing.heal_log import HealEvent
    from je_auto_control.utils.self_healing.evaluation import HealingEvaluationError

    class Unsafe:
        def __deepcopy__(self, memo):
            pytest.fail('audit validation ran an object hook')

    with pytest.raises(HealingEvaluationError):
        HealEvent('now', 'image', [1, 2], 1, context={'unsafe': Unsafe()})
    path = tmp_path / 'future.jsonl'
    path.write_text(json.dumps({'timestamp': 'future', 'method': 'image', 'coordinates': [1, 2],
                                'duration_ms': 1, 'schema_version': 99}) + '\n', encoding='utf-8')
    assert HealEventLog(path).list_events() == []


def test_fixed_geometry_is_independent_of_mutable_caller_input():
    from je_auto_control.utils.self_healing.evaluation import EvaluationSample
    origin, scale, box = [0, 0], [1, 1], [0, 0, 5, 5]
    item = EvaluationSample(b'fixed', origin=origin, scale=scale, expected_box=box, sample_id='immutable')
    origin[0], scale[0], box[0] = 100, 2, 200
    report = compare([item], {'v1': FakeStrategy({'immutable': (2, 2)})}).versions['v1']
    assert report.correct == 1
    assert item.origin == (0, 0) and item.scale == (1, 1) and item.expected_box == (0, 0, 5, 5)
