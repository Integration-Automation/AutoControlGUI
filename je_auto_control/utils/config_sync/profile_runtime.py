"""Construct disabled native hotkey and trigger objects without registering listeners or polling a backend."""
from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING, TypedDict, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError

if TYPE_CHECKING:
    from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyBinding
    from je_auto_control.utils.triggers.trigger_engine import (
        AllOfTrigger, AnyOfTrigger, CronTrigger, FilePathTrigger, ImageAppearsTrigger,
        PixelColorTrigger, SequenceTrigger, WindowAppearsTrigger, _TriggerBase,
    )


class _TriggerArguments(TypedDict):
    trigger_id: str
    script_path: str
    repeat: bool
    cooldown_seconds: float
    enabled: bool


def native_hotkeys(records: dict[str, dict[str, object]]) -> tuple[HotkeyBinding, ...]:
    """Create disabled registrations as data; daemon.bind and platform combo parsers are never called."""
    if not records:
        return ()
    # Native subsystems own executor-backed defaults: resolve them only for explicit nonempty native loading.
    native = import_module('je_auto_control.utils.hotkey.hotkey_daemon')
    binding_type: type[HotkeyBinding] = native.HotkeyBinding
    result = []
    for identifier, value in records.items():
        if value.get('enabled') is not False:
            raise ConfigSyncError('loaded hotkey definitions must be disabled')
        combo = cast(str, value['combo'])
        native.split_combo(combo)
        result.append(binding_type(identifier, combo, cast(str, value['script_path']), enabled=False))
    return tuple(result)


def native_triggers(records: dict[str, dict[str, object]]) -> tuple[_TriggerBase, ...]:
    """Construct real native conditions and composites while keeping every node disabled."""
    if not records:
        return ()
    native = import_module('je_auto_control.utils.triggers.trigger_engine')
    return tuple(_trigger(identifier, value, 0, native) for identifier, value in records.items())


def _trigger(identifier: str, value: dict[str, object], depth: int, native: ModuleType) -> _TriggerBase:
    if depth > 16 or value.get('enabled') is not False:
        raise ConfigSyncError('loaded trigger definitions must be bounded and disabled')
    common: _TriggerArguments = {'trigger_id': identifier, 'script_path': cast(str, value['script_path']),
        'repeat': cast(bool, value['repeat']), 'cooldown_seconds': cast(float, value['cooldown_seconds']),
        'enabled': False}
    kind = cast(str, value['kind'])
    constructors: dict[str, type[AllOfTrigger] | type[AnyOfTrigger] | type[SequenceTrigger]] = {
        'all': native.AllOfTrigger, 'any': native.AnyOfTrigger, 'sequence': native.SequenceTrigger}
    if kind in constructors:
        children = [_trigger(identifier + ':' + str(index), child, depth + 1, native)
                    for index, child in enumerate(cast(list[dict[str, object]], value['children']))]
        return constructors[kind](**common, children=children)
    condition = cast(dict[str, object], value['condition'])
    return _condition(kind, common, condition, native)


def _condition(kind: str, common: _TriggerArguments, values: dict[str, object], native: ModuleType) -> _TriggerBase:
    if kind == 'file':
        file_type: type[FilePathTrigger] = native.FilePathTrigger
        return file_type(**common, watch_path=cast(str, values['watch_path']))
    if kind == 'image':
        image_type: type[ImageAppearsTrigger] = native.ImageAppearsTrigger
        return image_type(**common, image_path=cast(str, values['image_path']),
                                   threshold=cast(float, values['threshold']))
    if kind == 'window':
        window_type: type[WindowAppearsTrigger] = native.WindowAppearsTrigger
        return window_type(**common, title_substring=cast(str, values['title_substring']),
                                    case_sensitive=cast(bool, values['case_sensitive']))
    if kind == 'pixel':
        rgb = cast(tuple[int, int, int], tuple(cast(list[int], values['target_rgb'])))
        pixel_type: type[PixelColorTrigger] = native.PixelColorTrigger
        return pixel_type(**common, x=cast(int, values['x']), y=cast(int, values['y']),
                                  target_rgb=rgb, tolerance=cast(int, values['tolerance']))
    if kind == 'cron':
        cron_type: type[CronTrigger] = native.CronTrigger
        return cron_type(**common, cron=cast(str, values['cron']))
    raise ConfigSyncError('unsupported native trigger condition')
