"""Verify installed-wheel recording excludes real kernel uinput nodes before open.

Shared by the kernel-event and sway/libinput containers. No physical host input
is opened. This proves injected-source exclusion, not physical device capture.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
from typing import Sequence

from je_auto_control.linux_wayland import input_events


def package_identity() -> str:
    """Refuse source-tree evidence or disabled verifier assertions."""
    if not __debug__:
        raise RuntimeError('native verification requires Python assertions enabled')
    location = Path(input_events.__file__).resolve(strict=True)
    assert 'site-packages' in location.parts, f'expected installed wheel, got {location}'
    assert sys.platform == 'linux', 'kernel source verification requires Linux'
    return str(location)


def source_paths() -> list[str]:
    """Select only ydotool kernel devices without opening any input node."""
    selected = []
    for entry in sorted(Path('/sys/class/input').glob('event*')):
        if re.fullmatch(r'event\d+', entry.name) is None:
            continue
        name = (entry / 'device/name').read_text(encoding='utf-8').strip().lower()
        if 'ydotool' in name:
            selected.append('/dev/input/' + entry.name)
            assert len(selected) <= input_events.MAX_DEVICES, 'too many ydotool input sources'
    return selected


def source_identities(paths: Sequence[str]) -> dict[str, str]:
    """Require existing character nodes with independently checked sysfs identity."""
    assert 1 <= len(paths) <= input_events.MAX_DEVICES, 'require one to sixteen real virtual input sources'
    assert len(set(paths)) == len(paths), 'duplicate source paths are not native evidence'
    identities = {}
    for value in paths:
        node = Path(value).resolve(strict=True)
        assert node.parent == Path('/dev/input') and re.fullmatch(r'event\d+', node.name), value
        info = node.stat()
        # pylint: disable-next=no-member  # reason: native verifier checks Linux before this POSIX-only operation
        assert stat.S_ISCHR(info.st_mode) and os.major(info.st_rdev) == 13, 'expected kernel input node'
        kernel = (Path('/sys/class/input') / node.name / 'device').resolve(strict=True)
        assert kernel.is_relative_to('/sys/devices/virtual/input'), f'expected uinput identity, got {kernel}'
        identities[str(node)] = str(kernel)
    return identities


def deny_selected_open(selected: set[str]):
    """Fail immediately if the recorder tries to open an excluded device."""
    selected = {os.path.realpath(value) for value in selected}
    def guard(event, args):
        if event != 'open' or not args or isinstance(args[0], int):
            return
        value = os.path.realpath(os.fsdecode(args[0]))
        assert value not in selected, f'virtual source must be excluded before opening: {value}'
    return guard


def descriptor_names() -> set[str]:
    """Snapshot descriptors after the temporary procfs listing fd is gone."""
    return {name for name in os.listdir('/proc/self/fd') if Path('/proc/self/fd', name).exists()}


def verify_virtual_sources(paths: Sequence[str] | None = None) -> str:
    """Exercise the public recorder and retain machine-readable native evidence."""
    installed = package_identity()
    identities = source_identities(source_paths() if paths is None else paths)
    sys.addaudithook(deny_selected_open(set(identities)))
    before = descriptor_names()
    recorder = input_events.PhysicalRecorder()
    try:
        try:
            recorder.start([input_events.InputDevice(path) for path in identities])
        except input_events.RecordingUnavailable as failure:
            assert failure.state == 'unsupported' and 'virtual' in failure.reason, str(failure)
            assert failure.has_recovery_instruction and failure.recovery, 'missing actionable failure'
        else:
            raise AssertionError('a virtual source was accepted as physical input')
        assert not recorder.running and not recorder.devices, 'excluded sources must never start a worker'
        assert not recorder.stop(), 'excluded sources must not produce recorded injection events'
    finally:
        recorder.close()
        recorder.close()
    after = descriptor_names()
    assert before == after, f'descriptor leak: before={before}, after={after}'
    return json.dumps({'check': 'kernel_virtual_source_exclusion', 'sources': identities,
                       'module': installed, 'python': platform.python_version(),
                       'kernel': platform.release(), 'fds_before': len(before), 'fds_after': len(after),
                       'opened_virtual_sources': 0, 'recorded_events': 0}, sort_keys=True)
