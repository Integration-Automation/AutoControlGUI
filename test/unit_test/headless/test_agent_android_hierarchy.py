"""Bounded semantic XML decoding never lets source data grant text access or expand app scope."""
import json
from concurrent.futures import CancelledError
from dataclasses import replace
import xml.etree.ElementTree as ET

import pytest

from je_auto_control.utils.agent_runtime.android_hierarchy import AndroidHierarchySample, parse_android_hierarchy
from je_auto_control.utils.agent_runtime.android_input_evidence import parse_android_input_evidence
from je_auto_control.utils.agent_runtime.android_scope import parse_android_snapshot
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.observation_refs import resolve_action
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.verification import verify

from .test_agent_android_scope import DEVICE, PACKAGE, evidence, input_dump, policy_dump

NONCE = 'a' * 32
KEY = b'private-fixture-freshness-key-1234'


def node(changes=None, children=()):
    attrs = {'index': '0', 'text': '', 'resource-id': '', 'class': 'android.widget.FrameLayout',
             'package': PACKAGE, 'content-desc': '', 'checkable': 'false', 'checked': 'false',
             'clickable': 'false', 'enabled': 'true', 'focusable': 'false', 'focused': 'false',
             'scrollable': 'false', 'long-clickable': 'false', 'password': 'false', 'selected': 'false',
             'bounds': '[0,0][100,200]'}
    attrs.update(changes or {})
    result = ET.Element('node', attrs)
    result.extend(children)
    return result


def document(root=None, *, rotation='0'):
    tree = ET.Element('hierarchy', {'rotation': rotation})
    tree.append(node() if root is None else root)
    return ET.tostring(tree, encoding='utf-8', xml_declaration=True)


def native_evidence():
    snapshot = parse_android_snapshot(evidence(), DEVICE, PACKAGE)
    return parse_android_input_evidence(input_dump(), policy_dump(), snapshot)


def sample(raw=None, *, grants=()):
    proof = native_evidence()
    return AndroidHierarchySample(NONCE, proof.snapshot, proof.size, document() if raw is None else raw, grants)


def parse(value, *, proof=None, check=lambda: None, key=KEY):
    return parse_android_hierarchy(value, proof or native_evidence(), value.request_id, key, check)


def semantic_tree():
    return document(node({'resource-id': 'android:id/content'}, [
        node({'index': '0', 'class': 'android.widget.Button', 'text': 'Save', 'clickable': 'true',
              'resource-id': PACKAGE + ':id/save', 'bounds': '[10,10][40,40]'}),
        node({'index': '1', 'class': 'android.widget.EditText', 'text': 'private-editable-value'}),
        node({'index': '2', 'text': 'private-password', 'password': 'true'}),
    ]))


def test_no_plain_xml_text_is_authorized_and_review_cannot_reveal_password_or_editable_values():
    raw = semantic_tree()
    hidden = parse(sample(raw))
    assert hidden.text == '' and all(item['name'] == '' for item in hidden.elements)
    reviewed = parse(sample(raw, grants=('0/0', '0/1', '0/2')))
    result = reviewed.to_dict()
    assert result['text'] == 'Save'
    assert result['elements'][1]['bounds'] == [10, 10, 30, 30]
    assert result['elements'][1]['role'] == 'button' and result['elements'][1]['actionable'] is True
    assert all(item['sensitive'] for item in result['elements'][2:])
    assert not any(item['actionable'] for item in result['elements'][2:])
    assert 'private-' not in json.dumps(result)
    assert 'private-' not in repr(sample(raw))


def test_foreign_packages_and_descendants_never_escape_the_owned_app_scope():
    foreign = node({'index': '1', 'package': 'org.foreign.app', 'text': 'foreign-secret'}, [
        node({'package': PACKAGE, 'text': 'smuggled-own-package-secret'})])
    view = parse(sample(document(node(children=[node({'text': 'own label'}), foreign])), grants=('0/0',)))
    assert len(view.elements) == 2 and view.text == 'own label'
    assert 'secret' not in json.dumps(view.to_dict())
    with pytest.raises(AgentTaskError):
        parse(sample(document(node(children=[foreign])), grants=('0/1',)))


def test_sensitive_ancestor_overrides_descendant_text_grants():
    raw = document(node({'password': 'true'}, [node({'text': 'protected-child', 'clickable': 'true'})]))
    view = parse(sample(raw, grants=('0/0',)))
    assert view.text == '' and all(item['sensitive'] for item in view.elements)
    assert not any(item['actionable'] for item in view.elements)


@pytest.mark.parametrize('attrs', [
    {'safe': 'true'}, {'enabled': 'True'}, {'editable': '1'}, {'bounds': '[-1,0][10,10]'},
    {'bounds': '[0,0][101,200]'}, {'bounds': '[5,5][1,1]'}, {'index': '-1'},
    {'resource-id': 'org.foreign.app:id/secret'}, {'text': 'x' * 513},
])
def test_unknown_or_ambiguous_metadata_is_refused_without_echoing_source(attrs):
    with pytest.raises(AgentTaskError):
        parse(sample(document(node(attrs))))


@pytest.mark.parametrize('raw', [
    b'', b'\xff', b'\0', b'x' * 1_000_001, b'<hierarchy/>',
    b'<hierarchy rotation="0"><node/></hierarchy>',
    b'<hierarchy rotation="0"><!--hidden--></hierarchy>',
    b'<?custom value?><hierarchy rotation="0"/>',
    b'<!DOCTYPE hierarchy [<!ENTITY a "private-entity">]><hierarchy rotation="0">&a;</hierarchy>',
    b'<!DOCTYPE hierarchy SYSTEM "file:///private-host-file"><hierarchy rotation="0"/>',
    b'<?xml version="1.0" encoding="iso-8859-1"?><hierarchy rotation="0"/>',
], ids=lambda value: f'xml-bytes-{len(value)}')
def test_malformed_xml_entities_dtd_instructions_and_encodings_are_never_accepted(raw):
    with pytest.raises(AgentTaskError) as error:
        parse(sample(raw))
    assert 'private-' not in str(error.value)


@pytest.mark.parametrize('grants', [('0/9',), ('0', '0'), ['0'], (True,), ('0/00',)])
def test_text_authority_requires_unique_existing_host_paths(grants):
    with pytest.raises(AgentTaskError):
        parse(sample(grants=grants))


@pytest.mark.parametrize('change', ['nonce', 'window', 'size', 'size_bool', 'key'])
def test_reader_capture_must_match_exact_live_scope_and_private_key(change):
    value, proof = sample(), native_evidence()
    if change == 'nonce':
        with pytest.raises(AgentTaskError):
            parse_android_hierarchy(value, proof, 'b' * 32, KEY, lambda: None)
        return
    if change == 'window':
        changed = replace(value.snapshot, window=value.snapshot.window.replace('abc123', 'abc124'))
        value = replace(value, snapshot=changed)
    elif change == 'size':
        value = replace(value, size=(99, 200))
    elif change == 'size_bool':
        proof = replace(proof, size=(1, 200))
        value = replace(value, size=(True, 200))
    with pytest.raises(AgentTaskError):
        parse(value, proof=proof, key=b'short' if change == 'key' else KEY)


def test_fresh_request_ids_do_not_change_fingerprints_but_private_content_and_grants_do():
    original = sample(semantic_tree(), grants=('0/0',))
    first = parse(original)
    assert parse(replace(original, request_id='b' * 32)).signature == first.signature
    changed = replace(original, xml=original.xml.replace(b'private-password', b'different-secret'))
    assert parse(changed).signature != first.signature
    assert parse(replace(original, safe_text_paths=())).signature != first.signature
    assert parse(original, key=b'other-private-freshness-key-12345').signature != first.signature


def test_duplicate_siblings_and_excessive_depth_or_nodes_are_rejected():
    duplicate = document(node(children=[node(), node()]))
    deep = node()
    for _ in range(33):
        deep = node(children=[deep])
    wide = document(node(children=[node({'index': str(index)}) for index in range(1000)]))
    for raw in (duplicate, document(deep), wide):
        with pytest.raises(AgentTaskError):
            parse(sample(raw))


def test_cancellation_is_checked_during_decode_and_remains_the_primary_exception():
    count = [0]

    def check():
        count[0] += 1
        if count[0] == 3:
            raise CancelledError('cancel fixture')

    with pytest.raises(CancelledError):
        parse(sample(semantic_tree()), check=check)


def test_android_reference_requires_semantic_scope_and_an_actionable_element():
    view = parse(sample(semantic_tree(), grants=('0/0',)))
    data = {**view.to_dict(), 'identity': {'platform': 'android', 'coordinate_space': 'android_display',
                                        'hierarchy': view.revision}}
    arguments, _grounding = resolve_action('AC_android_tap', {}, {'element_index': 1}, data)
    assert arguments == {'x': 25, 'y': 25}
    for reference, current in [({'element_index': 2}, data), ({'image_point': [1, 2]}, data),
                               ({'element_index': 1}, {**data, 'identity': {'platform': 'desktop'}})]:
        with pytest.raises(AgentTaskError):
            resolve_action('AC_android_tap', {}, reference, current)


@pytest.mark.parametrize('extra', [
    {'semantic_observation': False}, {'semantic_observation': 0}, {'semantic_observation': 1},
    {'semantic_observation': None}, {'text_redacted': None}, {'text_redacted': 0},
    {'text_redacted': 1}, {'text_redacted': True}, {'elements': 'unavailable'}, {'elements': ['invalid']},
])
def test_absence_never_passes_from_unavailable_malformed_or_redacted_evidence(extra):
    spec = AgentTaskSpec.from_dict({'goal': 'verify scoped frame', 'allowed_tools': ['AC_android_tap'],
        'success_criteria': [{'kind': 'screen', 'spec': {'text_absent': 'Missing'}}]})
    observation = {'elements': [{'name': 'Saved', 'enabled': True}], **extra}
    assert verify(TaskPolicy(spec), [], observation)[0]['status'] == 'unknown'


@pytest.mark.parametrize('condition,status', [
    ({'text_present': 'Saved'}, 'passed'), ({'text_present': 'Missing'}, 'unknown'),
    ({'text_absent': 'Saved'}, 'failed'), ({'text_absent': 'Missing'}, 'unknown'),
    ({'text_present': ''}, 'unknown'), ({'text_absent': ''}, 'unknown'),
])
def test_partial_text_only_proves_a_reviewed_positive_match_or_known_contradiction(condition, status):
    spec = AgentTaskSpec.from_dict({'goal': 'verify reviewed frame', 'allowed_tools': ['AC_android_tap'],
        'success_criteria': [{'kind': 'screen', 'spec': condition}]})
    frame = {'elements': [{'name': 'Saved'}], 'text_redacted': True, 'semantic_observation': True}
    assert verify(TaskPolicy(spec), [], frame)[0]['status'] == status
