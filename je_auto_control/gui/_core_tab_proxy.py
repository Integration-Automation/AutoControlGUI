"""Lazy descriptors preserve legacy core-tab methods without importing unopened panels."""
from importlib import import_module
from typing import Any, Callable, Optional


class _LazyMethod:  # pylint: disable=too-few-public-methods  # reason: one descriptor binding protocol
    def __init__(self, module: str, cls: str, name: str) -> None:
        self._module, self._class, self._name = module, cls, name

    def __get__(self, instance: Optional[object], _owner: Optional[type[object]] = None) -> Callable[..., Any]:
        handler = getattr(getattr(import_module(self._module), self._class), self._name)
        return handler if instance is None else handler.__get__(instance, type(instance))


class CoreTabMethods:  # pylint: disable=too-few-public-methods  # reason: private legacy GUI method descriptors
    """Compatibility descriptors load one core mixin only when its method is accessed."""
    _build_auto_click_tab = _LazyMethod(
        'je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_build_auto_click_tab')
    _auto_click_retranslate = _LazyMethod(
        'je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_auto_click_retranslate')
    _update_click_mode = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_update_click_mode')
    _start_auto_click = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_start_auto_click')
    _stop_auto_click = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_stop_auto_click')
    _timer_tick = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_timer_tick')
    _do_click = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_do_click')
    _get_mouse_pos = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_get_mouse_pos')
    _send_hotkey = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_send_hotkey')
    _send_write = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_send_write')
    _send_scroll = _LazyMethod('je_auto_control.gui._auto_click_tab', 'AutoClickTabMixin', '_send_scroll')
    _build_screenshot_tab = _LazyMethod(
        'je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_build_screenshot_tab')
    _get_screen_size = _LazyMethod('je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_get_screen_size')
    _browse_ss_path = _LazyMethod('je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_browse_ss_path')
    _pick_ss_region = _LazyMethod('je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_pick_ss_region')
    _take_screenshot = _LazyMethod('je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_take_screenshot')
    _get_pixel_color = _LazyMethod('je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_get_pixel_color')
    _screenshot_retranslate = _LazyMethod(
        'je_auto_control.gui._screenshot_tab', 'ScreenshotTabMixin', '_screenshot_retranslate')
    _build_image_detect_tab = _LazyMethod(
        'je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_build_image_detect_tab')
    _browse_img = _LazyMethod('je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_browse_img')
    _crop_template = _LazyMethod('je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_crop_template')
    _get_detect_params = _LazyMethod(
        'je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_get_detect_params')
    _locate_image = _LazyMethod('je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_locate_image')
    _locate_all = _LazyMethod('je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_locate_all')
    _locate_click = _LazyMethod('je_auto_control.gui._image_detect_tab', 'ImageDetectTabMixin', '_locate_click')
    _build_record_tab = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_build_record_tab')
    _apply_record_status_label = _LazyMethod(
        'je_auto_control.gui._record_tab', 'RecordTabMixin', '_apply_record_status_label')
    _record_retranslate = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_record_retranslate')
    _start_record = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_start_record')
    _stop_record = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_stop_record')
    _playback_record = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_playback_record')
    _save_record = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_save_record')
    _load_record = _LazyMethod('je_auto_control.gui._record_tab', 'RecordTabMixin', '_load_record')
    _build_script_tab = _LazyMethod('je_auto_control.gui._script_tab', 'ScriptTabMixin', '_build_script_tab')
    _browse_script = _LazyMethod('je_auto_control.gui._script_tab', 'ScriptTabMixin', '_browse_script')
    _execute_script = _LazyMethod('je_auto_control.gui._script_tab', 'ScriptTabMixin', '_execute_script')
    _browse_script_dir = _LazyMethod('je_auto_control.gui._script_tab', 'ScriptTabMixin', '_browse_script_dir')
    _execute_dir = _LazyMethod('je_auto_control.gui._script_tab', 'ScriptTabMixin', '_execute_dir')
    _execute_manual_script = _LazyMethod('je_auto_control.gui._script_tab', 'ScriptTabMixin', '_execute_manual_script')
    _build_report_tab = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_build_report_tab')
    _set_test_record = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_set_test_record')
    _enable_test_record = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_enable_test_record')
    _disable_test_record = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_disable_test_record')
    _gen_html = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_gen_html')
    _gen_json = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_gen_json')
    _gen_xml = _LazyMethod('je_auto_control.gui._report_tab', 'ReportTabMixin', '_gen_xml')
