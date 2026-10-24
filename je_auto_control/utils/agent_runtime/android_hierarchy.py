"""Parse bounded Android app hierarchies with explicit host text grants and private freshness signatures."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from je_auto_control.utils.agent_runtime.android_input_evidence import AndroidInputEvidence
from je_auto_control.utils.agent_runtime.android_scope import AndroidSnapshot
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached, freeze

_FLAGS = frozenset({'checkable', 'checked', 'clickable', 'enabled', 'focusable', 'focused', 'scrollable',
                    'long-clickable', 'password', 'selected'})
_FIELDS = _FLAGS | {'index', 'text', 'resource-id', 'class', 'package', 'content-desc', 'bounds'}
_OPTIONAL = frozenset({'NAF', 'editable', 'visible-to-user'})
_INDEX = re.compile(r'0|[1-9][0-9]{0,4}')
_PATH = re.compile(r'0(?:/(?:0|[1-9][0-9]{0,4})){0,31}')
_BOUNDS = re.compile(r'\[(0|[1-9][0-9]{0,4}),(0|[1-9][0-9]{0,4})\]'
                     r'\[(0|[1-9][0-9]{0,4}),(0|[1-9][0-9]{0,4})\]')
_ROLES = {'android.widget.Button': 'button', 'android.widget.ImageButton': 'button',
          'android.widget.CheckBox': 'checkbox', 'android.widget.RadioButton': 'radio',
          'android.widget.Switch': 'switch', 'android.widget.EditText': 'textfield',
          'android.widget.TextView': 'text', 'android.widget.ImageView': 'image'}


@dataclass(frozen=True)
class AndroidHierarchySample:
    """Trusted reader result, never model authority; text grants require fresh host non-sensitive/read-only review.

    Readers must attest the actual source device/window and preserve other accessibility owners.
    Echoing requested metadata around an unverified SDK result is not a source attestation.
    Plain XML never grants permission to reveal text, including editable values.
    """

    request_id: str
    snapshot: AndroidSnapshot
    size: tuple[int, int]
    xml: bytes = field(repr=False)
    safe_text_paths: tuple[str, ...] = ()


# pylint: disable-next=too-few-public-methods  # reason: keyword-only capture callable is the complete protocol
class AndroidHierarchyReader(Protocol):
    """Explicit host capture seam; no default device, SDK startup, CLI, retries or fallback."""

    def __call__(self, evidence: AndroidInputEvidence, request_id: str, *, timeout: float,
                 check: Callable[[], None]) -> AndroidHierarchySample:
        """Read fresh bounded hierarchy on the proven device/window without disturbing other service owners."""


@dataclass(frozen=True)
class AndroidHierarchyView:
    """Sanitized flat app elements and a keyed signature; raw XML/password values are never published."""

    signature: str = field(repr=False)
    elements: tuple[Mapping[str, Any], ...]
    text: str
    text_redacted: bool
    revision: str = field(default_factory=lambda: secrets.token_hex(32))

    def same_source(self, other: AndroidHierarchyView) -> bool:
        """Compare private source witnesses without publishing a reusable fingerprint of hidden values."""
        return hmac.compare_digest(self.signature, other.signature)

    def to_dict(self) -> dict:
        """Return detached semantic readback without the raw source or any text-authority token."""
        return detached({'elements': self.elements, 'text': self.text,
                         'text_redacted': self.text_redacted, 'semantic_observation': True})


@dataclass
class _Frame:
    path: str
    skipped: bool = False
    protected: bool = False
    enabled: bool = True
    visible: bool = True
    indices: set[str] = field(default_factory=set)


def parse_android_hierarchy(sample: AndroidHierarchySample, evidence: AndroidInputEvidence,
                            request_id: str, key: bytes, check: Callable[[], None]) -> AndroidHierarchyView:
    """Reject XXE/DTD, malformed scopes and unreviewed content; check cancellation at every XML event."""
    _sample_scope(sample, evidence, request_id, key)
    builder = _HierarchyBuilder(evidence, frozenset(sample.safe_text_paths))
    try:
        stream = io.StringIO(_decode_xml(sample.xml))
        for event, node in SafeET.iterparse(stream, events=('start', 'end', 'pi', 'comment'),
                                            forbid_dtd=True, forbid_entities=True, forbid_external=True):
            check()
            builder.consume(event, node)
    except (DefusedXmlException, SafeET.ParseError, UnicodeError):
        raise AgentTaskError('Android hierarchy XML is malformed or unsafe; diagnostics are withheld') from None
    elements = builder.finish()
    grants = json.dumps(sorted(sample.safe_text_paths), separators=(',', ':')).encode('ascii')
    signature = hmac.new(key, sample.xml + b'\0' + grants, hashlib.sha256).hexdigest()
    text = '\n'.join(item['name'] for item in elements if item['name'])
    if len(text) > 16384:
        raise AgentTaskError('Android reviewed hierarchy text exceeds its output bound')
    check()
    return AndroidHierarchyView(signature, freeze(elements), text, any(item['text_redacted'] for item in elements))


def _sample_scope(sample: AndroidHierarchySample, evidence: AndroidInputEvidence, request_id: str, key: bytes) -> None:
    if not isinstance(sample, AndroidHierarchySample) or not isinstance(sample.snapshot, AndroidSnapshot):
        raise AgentTaskError('Android hierarchy source does not match the current native window')
    if (sample.snapshot != evidence.snapshot or sample.request_id != request_id
            or not _valid_size(sample.size) or sample.size != evidence.size):
        raise AgentTaskError('Android hierarchy request/display identity is incompatible')
    _capture_tokens(request_id, key)
    if not isinstance(sample.xml, bytes) or not 1 <= len(sample.xml) <= 1_000_000 or b'\0' in sample.xml:
        raise AgentTaskError('Android hierarchy requires bounded UTF-8 XML')
    _text_grants(sample.safe_text_paths)


def _capture_tokens(request_id: str, key: bytes) -> None:
    if not isinstance(request_id, str) or re.fullmatch('[0-9a-f]{32}', request_id) is None:
        raise AgentTaskError('Android hierarchy requires an exact capture request identity')
    if not isinstance(key, bytes) or len(key) < 32:
        raise AgentTaskError('Android hierarchy requires a private host freshness key')


def _valid_size(size: tuple[int, int]) -> bool:
    return (isinstance(size, tuple) and len(size) == 2
            and all(isinstance(part, int) and not isinstance(part, bool) and 0 < part <= 16384 for part in size))


def _decode_xml(raw: bytes) -> str:
    text = raw.decode('utf-8-sig')
    if text.startswith('<?xml'):
        header, separator, _body = text.partition('?>')
        encoding = re.search(r'''\bencoding\s*=\s*(['"])([^'"]+)\1''', header)
        if not separator or len(header) > 1024 or (encoding and encoding[2].lower() != 'utf-8'):
            raise AgentTaskError('Android hierarchy XML encoding is unsupported')
    return text


def _text_grants(paths: tuple[str, ...]) -> None:
    if not isinstance(paths, tuple) or len(paths) > 1000:
        raise AgentTaskError('Android hierarchy requires explicit bounded host text grants')
    if any(not isinstance(path, str) or _PATH.fullmatch(path) is None for path in paths):
        raise AgentTaskError('Android hierarchy host text grant has an invalid path')
    if len(set(paths)) != len(paths):
        raise AgentTaskError('Android hierarchy host text grants are ambiguous')


class _HierarchyBuilder:
    """Bound streaming decode before constructing the flat, protected app-only result."""

    def __init__(self, evidence: AndroidInputEvidence, grants: frozenset[str]) -> None:
        self.evidence, self.grants = evidence, grants
        self.stack: list[_Frame] = []
        self.seen: set[str] = set()
        self.elements: list[dict] = []
        self.count = 0
        self.root_seen = False

    def consume(self, event: str, node: Any) -> None:
        """Validate one XML event before retaining any sanitized node metadata."""
        if event == 'end':
            if (node.text and node.text.strip()) or (node.tail and node.tail.strip()):
                raise AgentTaskError('Android hierarchy contains unsupported XML text')
            self.stack.pop()
            node.clear()
        elif event == 'start':
            self._start(node)
        else:
            raise AgentTaskError('Android hierarchy contains unsupported XML instructions')

    def _start(self, node: Any) -> None:
        if not self.stack:
            self._root(node)
            return
        self.count += 1
        if self.count > 4096 or len(self.stack) > 32 or node.tag != 'node':
            raise AgentTaskError('Android hierarchy node/depth/schema bound exceeded')
        parent = self.stack[-1]
        attrs, flags = _attributes(node.attrib)
        frame = _node_frame(parent, attrs, flags, self.evidence.snapshot.package)
        if not parent.path and (frame.skipped or len(parent.indices) != 1):
            raise AgentTaskError('Android hierarchy active root does not match its app scope')
        self.seen.add(frame.path)
        self.stack.append(frame)
        self._element(attrs, flags, frame, parent.visible)

    def _root(self, node: Any) -> None:
        if self.root_seen or node.tag != 'hierarchy' or node.attrib != {'rotation': '0'}:
            raise AgentTaskError('Android hierarchy requires one supported default-display root')
        self.root_seen = True
        self.stack.append(_Frame(''))

    def _element(self, attrs: dict, flags: dict, frame: _Frame, parent_visible: bool) -> None:
        bounds = _bounds(attrs['bounds'], self.evidence.size)
        frame.visible = _visible(parent_visible, flags, bounds)
        if frame.skipped:
            if frame.path in self.grants:
                raise AgentTaskError('Android hierarchy text grant is outside its app scope')
            return
        if len(self.elements) >= 1000:
            raise AgentTaskError('Android hierarchy output element bound exceeded')
        data = _node_data(attrs, flags, frame, self.grants)
        data.update(index=len(self.elements), bounds=bounds,
                    resource_id=_resource_id(attrs['resource-id'], self.evidence.snapshot.package),
                    actionable=data['actionable'] and _point_allowed(self.evidence, bounds))
        self.elements.append(data)

    def finish(self) -> list[dict]:
        """Never accept missing grants, empty/multiple roots or unfinished XML state."""
        if self.stack or not self.root_seen or not self.elements or not self.grants <= self.seen:
            raise AgentTaskError('Android hierarchy is incomplete or has stale text grants')
        return self.elements


def _node_frame(parent: _Frame, attrs: dict, flags: dict, package: str) -> _Frame:
    index = attrs['index']
    if index in parent.indices or (not parent.path and index != '0'):
        raise AgentTaskError('Android hierarchy sibling index is ambiguous')
    parent.indices.add(index)
    path = parent.path + '/' + index if parent.path else index
    return _Frame(path, parent.skipped or attrs['package'] != package,
                  parent.protected or flags['password'] or flags.get('editable', False)
                  or attrs['class'] == 'android.widget.EditText', parent.enabled and flags['enabled'])


def _visible(parent: bool, flags: dict, bounds: list[int]) -> bool:
    return parent and flags.get('visible-to-user', True) and bounds[2] > 0 and bounds[3] > 0


def _node_data(attrs: dict, flags: dict, frame: _Frame, grants: frozenset[str]) -> dict:
    name, text = '', ''
    reviewed = frame.path in grants and not frame.protected and frame.visible
    if reviewed:
        text = attrs['text']
        name = attrs['content-desc'] or text
    actionable = frame.enabled and frame.visible and flags['clickable'] and not frame.protected
    return {'native_id': frame.path, 'role': _ROLES.get(attrs['class'], 'view'), 'name': name, 'text': text,
            'enabled': frame.enabled, 'visible': frame.visible, 'actionable': actionable,
            'checked': flags['checked'], 'selected': flags['selected'], 'sensitive': frame.protected,
            'text_redacted': not reviewed}


def _attributes(attrs: dict) -> tuple[dict, dict[str, bool]]:
    if _FIELDS - set(attrs) or set(attrs) - (_FIELDS | _OPTIONAL):
        raise AgentTaskError('Android hierarchy node attributes are unsupported')
    if any(len(value) > 512 for value in attrs.values()) or _INDEX.fullmatch(attrs['index']) is None:
        raise AgentTaskError('Android hierarchy node attribute bound exceeded')
    flags = {}
    for name in (_FLAGS | _OPTIONAL) & set(attrs):
        if attrs[name] not in {'true', 'false'}:
            raise AgentTaskError('Android hierarchy requires exact boolean metadata')
        flags[name] = attrs[name] == 'true'
    return attrs, flags


def _bounds(value: str, size: tuple[int, int]) -> list[int]:
    match = _BOUNDS.fullmatch(value)
    if match is None:
        raise AgentTaskError('Android hierarchy bounds are unsupported')
    left, top, right, bottom = (int(part) for part in match.groups())
    if not 0 <= left <= right <= size[0] or not 0 <= top <= bottom <= size[1]:
        raise AgentTaskError('Android hierarchy bounds are outside the native display')
    return [left, top, right - left, bottom - top]


def _resource_id(value: str, package: str) -> str:
    pattern = '(?:' + re.escape(package) + r'|android):id/[A-Za-z_][A-Za-z0-9_]*'
    if value and (len(value) > 255 or re.fullmatch(pattern, value) is None):
        raise AgentTaskError('Android hierarchy resource identity is unsupported')
    return value


def _point_allowed(evidence: AndroidInputEvidence, bounds: list[int]) -> bool:
    point = (bounds[0] + bounds[2] // 2, bounds[1] + bounds[3] // 2)
    try:
        evidence.require_path(point, point)
        return True
    except AgentTaskError:
        return False
