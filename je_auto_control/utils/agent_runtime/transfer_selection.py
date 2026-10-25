"""Resolve only source-owned passed file criteria and their explicitly selected manifest names."""
from __future__ import annotations

import codecs
import json
from pathlib import Path
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_files import snapshot_file
from je_auto_control.utils.agent_runtime.transfer_models import MAX_TRANSFER_BYTES, TransferSelection, _hex


class TextCriterion:
    """Match actual UTF-8 source bytes across chunk boundaries without keeping the whole file in RAM."""

    def __init__(self, value: str) -> None:
        self._decoder = codecs.getincrementaldecoder('utf-8')()
        self._expected = value
        self._tail = ''
        self._found = value == ''

    def feed(self, body: bytes) -> None:
        """Decode one actual snapshot chunk and retain only the possible match overlap."""
        self._decode(body, final=False)

    def finish(self) -> None:
        """Reject malformed/truncated UTF-8 or bytes which no longer satisfy the selected text condition."""
        self._decode(b'', final=True)
        if not self._found:
            raise AgentTaskError('source bytes no longer satisfy the selected text criterion')

    def _decode(self, body: bytes, *, final: bool) -> None:
        try:
            window = self._tail + self._decoder.decode(body, final=final)
        except UnicodeError as error:
            raise AgentTaskError('source text no longer contains valid UTF-8') from error
        self._found = self._found or self._expected in window
        self._tail = window[-(len(self._expected) - 1):] if len(self._expected) > 1 else ''


def selected_files(context: dict, values: Any, checkpoint: Callable[[], None]) -> list[tuple[str, dict]]:
    """Compile exact source criteria; no request path or replacement filename is accepted."""
    selections = _selections(values)
    criteria = context['row']['spec']['success_criteria']
    result = []
    for selection in selections:
        checkpoint()
        if selection.criterion >= len(criteria):
            raise AgentTaskError('selected criterion is outside the completed source')
        clause = criteria[selection.criterion]
        result.extend(_selected_clause(context['policy'], clause, selection, checkpoint))
        if len(result) > 500:
            raise AgentTaskError('export selection exceeds five hundred files')
    return result


def _selections(values: Any) -> list[TransferSelection]:
    if not isinstance(values, list) or not 1 <= len(values) <= 500:
        raise AgentTaskError('export requires one to five hundred explicit selections')
    selections = [TransferSelection.from_dict(value) for value in values]
    if len({item.criterion for item in selections}) != len(selections):
        raise AgentTaskError('export criteria cannot be selected twice')
    return selections


def _selected_clause(policy: Any, clause: dict, selection: TransferSelection,
                      checkpoint: Callable[[], None]) -> list[tuple[str, dict]]:
    if clause['kind'] == 'file_manifest':
        return _manifest_selection(policy, clause, selection, checkpoint)
    if clause['kind'] in {'file_exists', 'file_sha256', 'file_text'} and not selection.names:
        return [(clause['path'], clause)]
    raise AgentTaskError('selected criterion is not an explicit supported source file')


def _manifest_selection(policy: Any, clause: dict, selection: TransferSelection,
                        checkpoint: Callable[[], None]) -> list[tuple[str, dict]]:
    if not selection.names or not set(selection.names) <= set(clause['names']):
        raise AgentTaskError('manifest selection must explicitly name original source outputs')
    pieces: list[bytes] = []
    source = snapshot_file(policy, clause['path'], checkpoint, max_bytes=1_000_000, inspect=pieces.append)
    try:
        document = json.loads(b''.join(pieces).decode('utf-8'))
    except (ValueError, UnicodeError) as error:
        raise AgentTaskError('source file manifest is malformed') from error
    if (not isinstance(document, dict) or set(document) != {'files'} or not isinstance(document['files'], list)
            or len(document['files']) != len(clause['names'])):
        raise AgentTaskError('source file manifest no longer matches its completed criterion')
    entries = {}
    directory = Path(policy.path(clause['directory']))
    for name, entry in zip(clause['names'], document['files']):
        path = directory / name
        _manifest_entry(entry, name, path)
        entries[name] = (str(path), {'kind': 'file_sha256', 'value': entry['sha256'],
                                   'expected_size': entry['bytes'], 'manifest_witness': list(source.witness),
                                   'manifest_sha256': source.blob.sha256})
    return [entries[name] for name in selection.names]


def _manifest_entry(entry: Any, name: str, path: Path) -> None:
    if not isinstance(entry, dict) or set(entry) != {'path', 'name', 'bytes', 'sha256'}:
        raise AgentTaskError('source manifest contains unknown or invalid entry fields')
    size = entry['bytes']
    if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_TRANSFER_BYTES:
        raise AgentTaskError('source manifest contains an invalid file size')
    _hex(entry['sha256'], 64)
    if entry['name'] != name or entry['path'] != str(path):
        raise AgentTaskError('source manifest cannot replace original paths or output names')
