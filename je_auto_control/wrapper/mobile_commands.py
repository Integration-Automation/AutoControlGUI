"""The one description of every ``AC_android_*`` / ``AC_ios_*`` command.

A mobile capability is only delivered when it can be reached from a JSON
action file, from an MCP client, from the Script Builder and from the GUI.
Writing each of those by hand is how the adb commands ended up with executor
entries but no builder schema and no MCP tool. So the commands are described
once, here, in :data:`MOBILE_COMMANDS`, and the surfaces are generated:

* the executor takes :func:`generated_handlers`;
* the MCP registry takes :func:`mcp_tool_specs`;
* the Script Builder schema and the Mobile tab read :data:`MOBILE_COMMANDS`.

Commands that existed before the table are listed too (``legacy``): their
handlers stay where they were, in ``action_executor``, and the table carries
their parameters so the other surfaces cover them.
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

from je_auto_control.wrapper import mobile_extensions as extensions
from je_auto_control.wrapper.device_context import (
    CAPABILITY_NAMES, DEFAULT_TIMEOUT_S, PLATFORM_ANDROID, PLATFORM_IOS, AppState,
    DeviceContext, DeviceError, DeviceSession, DeviceSetupReport, Drag, LongPress,
    Pinch, Tap, bound_session, open_device,
)

_KINDS = {"int": int, "float": float, "bool": bool, "string": str, "file_path": str}
_JSON_TYPES = {"int": "integer", "float": "number", "bool": "boolean"}


@dataclass(frozen=True)
class Param:
    """One command parameter. ``kind`` is int, float, bool, string or file_path."""

    name: str
    kind: str = "string"
    required: bool = False
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class MobileCommand:
    """One ``AC_*`` mobile command and everything a surface needs to offer it."""

    name: str
    platform: str
    label: str
    description: str
    params: Tuple[Param, ...]
    capability: str
    api: str
    read_only: bool = False
    #: Handled by a function that predates the table, in ``action_executor``.
    legacy: bool = False
    #: An MCP tool for it was already written by hand in ``_factories``.
    handwritten_mcp: bool = False

    @property
    def mcp_name(self) -> str:
        """The MCP tool name: ``AC_android_tap`` is ``ac_android_tap``."""
        return "ac_" + self.name[3:]


#: Commands deliberately not offered as MCP tools, with the reason.
MCP_EXCLUDED: Mapping[str, str] = {
    "AC_android_shell": "runs an arbitrary shell command on the device; kept to action "
                        "files, where the author of the script is the one choosing it",
}

_ADDRESS = {
    PLATFORM_ANDROID: (
        Param("serial", description="adb serial; omit for the bound or only device"),
        Param("adb_path", description="adb binary; omit to use PATH"),
        Param("device_timeout_s", "float", description="per-call timeout, default 30"),
    ),
    PLATFORM_IOS: (
        Param("url", description="WebDriverAgent URL; omit for the bound or default device"),
        Param("device_timeout_s", "float", description="per-call timeout, default 30"),
    ),
}
_ADDRESS_NAMES = ("serial", "url", "adb_path", "device_timeout_s")


@contextmanager
def command_session(platform: str, device_id: Optional[str] = None, *,
                    adb_path: Optional[str] = None,
                    timeout_s: Optional[float] = None) -> Iterator[DeviceSession]:
    """The session a command runs on: the bound one when it is addressed, else a new one.

    A session opened here is closed when the command returns; a bound session
    (``use_device``, a device-matrix worker) is left to whoever bound it.
    """
    bound = bound_session(platform, device_id or None)
    if bound is not None:
        yield bound
        return
    session = open_device(DeviceContext(
        platform, device_id or "", adb_path=adb_path or None,
        timeout_s=float(timeout_s) if timeout_s else DEFAULT_TIMEOUT_S))
    try:
        yield session
    finally:
        session.close()


def device_setup_report(session: DeviceSession) -> DeviceSetupReport:
    """Backend, versions and capabilities of ``session``'s device. Sends no input."""
    return session.setup_report()


# --- what each operation does, on any session ---------------------------

def _device_info(session: DeviceSession) -> Dict[str, Any]:
    return device_setup_report(session).to_dict()


def _screen_info(session: DeviceSession) -> Dict[str, Any]:
    return dict(session.capture().to_dict())


def _type_text(session: DeviceSession, text: str) -> None:
    session.type_text(text)


def _press_key(session: DeviceSession, key: str) -> None:
    session.press_key(key)


def _long_press(session: DeviceSession, x: int, y: int, duration_s: float = 1.0) -> None:
    session.perform(LongPress(x, y, duration_s))


def _drag(session: DeviceSession, x1: int, y1: int, x2: int, y2: int,
          hold_s: float = 0.5, duration_s: float = 0.5) -> None:
    session.perform(Drag(x1, y1, x2, y2, hold_s, duration_s))


def _pinch(session: DeviceSession, x: int, y: int, scale: float,
           duration_s: float = 0.5, span: int = 400) -> None:
    session.perform(Pinch(x, y, scale, duration_s, span))


def _located(session: DeviceSession, point: Optional[Tuple[int, int]],
             tap: bool) -> Dict[str, Any]:
    """The result of a locate, tapping the point first when asked."""
    if point is None:
        return {"found": False}
    if tap:
        session.perform(Tap(int(point[0]), int(point[1])))
    return {"found": True, "x": int(point[0]), "y": int(point[1]), "tapped": bool(tap)}


def _find_image(session: DeviceSession, template_path: str,
                detect_threshold: float = 0.9, tap: bool = False) -> Dict[str, Any]:
    return _located(session, session.capture().locate_image(template_path, detect_threshold), tap)


def _find_text(session: DeviceSession, text: str, lang: str = "eng",
               min_confidence: float = 60.0, tap: bool = False) -> Dict[str, Any]:
    point = session.capture().locate_text(text, lang=lang, min_confidence=min_confidence)
    return _located(session, point, tap)


def _find_by_description(session: DeviceSession, description: str,
                         model: Optional[str] = None, tap: bool = False) -> Dict[str, Any]:
    return _located(session, session.capture().locate_description(description, model=model), tap)


def _self_heal(session: DeviceSession, template_path: Optional[str] = None,
               description: Optional[str] = None, detect_threshold: float = 0.9,
               model: Optional[str] = None, tap: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.self_healing.locator import self_heal_locate
    outcome = self_heal_locate(
        template_path=template_path, description=description,
        detect_threshold=detect_threshold, model=model, frame=session.capture())
    if tap and outcome.found and outcome.coordinates is not None:
        session.perform(Tap(*outcome.coordinates))
    return outcome.to_dict()


def _launch_app(session: DeviceSession, app_id: str) -> str:
    return str(extensions.launch_app(session, app_id).value)


def _stop_app(session: DeviceSession, app_id: str) -> str:
    return str(extensions.stop_app(session, app_id).value)


def _app_state(session: DeviceSession, app_id: str) -> str:
    return str(extensions.app_state(session, app_id).value)


def _wait_for_app(session: DeviceSession, app_id: str, timeout_s: float = 10.0,
                  state: str = "foreground") -> str:
    try:
        wanted = AppState(state)
    except ValueError as error:
        raise DeviceError(f"unknown app state {state!r}") from error
    return str(extensions.wait_for_app(session, app_id, timeout_s=timeout_s, state=wanted).value)


def _alert_accept(session: DeviceSession) -> str:
    return extensions.accept_alert(session)


def _alert_dismiss(session: DeviceSession) -> str:
    return extensions.dismiss_alert(session)


def _install_app(session: DeviceSession, path: str) -> str:
    return extensions.mobile_extension(session).install_app(path)


def _push_file(session: DeviceSession, local_path: str, remote_path: str) -> str:
    return extensions.mobile_extension(session).push_file(local_path, remote_path)


def _pull_file(session: DeviceSession, remote_path: str, local_path: str) -> str:
    return extensions.mobile_extension(session).pull_file(remote_path, local_path)


def _get_clipboard(session: DeviceSession) -> str:
    return extensions.mobile_extension(session).get_clipboard()


def _set_clipboard(session: DeviceSession, text: str) -> None:
    extensions.mobile_extension(session).set_clipboard(text)


def _start_recording(session: DeviceSession, **options: Any) -> str:
    return extensions.mobile_extension(session).start_recording(**options)


def _stop_recording(session: DeviceSession, local_path: str, **options: Any) -> str:
    return extensions.mobile_extension(session).stop_recording(local_path, **options)


@dataclass(frozen=True)
class _Operation:
    """One session operation, offered as a command on each platform it lists."""

    key: str
    label: str
    description: str
    run: Callable[..., Any]
    params: Tuple[Param, ...] = ()
    capability: str = "input"
    api: str = "DeviceSession"
    read_only: bool = False
    platforms: Tuple[str, ...] = (PLATFORM_ANDROID, PLATFORM_IOS)


_XY = (Param("x", "int", True), Param("y", "int", True))
_TAP = Param("tap", "bool", default=False, description="tap the point when found")
_APP = (Param("app_id", required=True, description="Android package or iOS bundle id"),)

_OPERATIONS: Tuple[_Operation, ...] = (
    _Operation("device_info", "Device Info",
               "Backend, versions and capabilities of the device. Sends no input.",
               _device_info, api="device_setup_report", read_only=True),
    _Operation("screen_info", "Screen Info",
               "Pixel size, point size, scale and orientation of the current screen.",
               _screen_info, capability="screenshot", api="DeviceFrame", read_only=True),
    _Operation("type_text", "Type Text (Unicode)",
               "Type text through a path that can carry it; raises when none can.",
               _type_text, (Param("text", required=True),), "unicode_text",
               platforms=(PLATFORM_ANDROID,)),
    _Operation("press_key", "Press Key", "Press a hardware key (home, volumeUp, volumeDown).",
               _press_key, (Param("key", required=True),), platforms=(PLATFORM_IOS,)),
    _Operation("long_press", "Long Press", "Press and hold at a point.", _long_press,
               _XY + (Param("duration_s", "float", default=1.0),), api="LongPress"),
    _Operation("drag", "Drag", "Press, hold so the item lifts, and move it.", _drag,
               (Param("x1", "int", True), Param("y1", "int", True),
                Param("x2", "int", True), Param("y2", "int", True),
                Param("hold_s", "float", default=0.5),
                Param("duration_s", "float", default=0.5)), api="Drag"),
    _Operation("pinch", "Pinch", "Two-finger pinch: scale above 1 zooms in, below 1 out.",
               _pinch, _XY + (Param("scale", "float", True),
                              Param("duration_s", "float", default=0.5),
                              Param("span", "int", default=400)),
               "multi_touch", "Pinch"),
    _Operation("find_image", "Find Image",
               "Template-match in the device screen; answers in device points.", _find_image,
               (Param("template_path", "file_path", True),
                Param("detect_threshold", "float", default=0.9), _TAP),
               "screenshot", "DeviceFrame"),
    _Operation("find_text", "Find Text (OCR)",
               "OCR the device screen for text; answers in device points.", _find_text,
               (Param("text", required=True), Param("lang", default="eng"),
                Param("min_confidence", "float", default=60.0), _TAP),
               "screenshot", "DeviceFrame"),
    _Operation("find_by_description", "Find By Description (VLM)",
               "Ask a vision-language model where something is on the device screen.",
               _find_by_description,
               (Param("description", required=True), Param("model"), _TAP),
               "screenshot", "DeviceFrame"),
    _Operation("self_heal", "Self-Heal Locate",
               "Template first, VLM on a miss, against the device screen.", _self_heal,
               (Param("template_path", "file_path"), Param("description"),
                Param("detect_threshold", "float", default=0.9), Param("model"), _TAP),
               "screenshot", "self_heal_locate"),
    _Operation("launch_app", "Launch App", "Launch an app; returns its state.", _launch_app,
               _APP, "app_lifecycle", "launch_app"),
    _Operation("stop_app", "Stop App", "Stop an app; returns its state.", _stop_app,
               _APP, "app_lifecycle", "stop_app"),
    _Operation("app_state", "App State",
               "not_installed, not_running, background or foreground.", _app_state,
               _APP, "app_lifecycle", "app_state", read_only=True),
    _Operation("wait_for_app", "Wait For App",
               "Wait until an app reaches a state; raises on timeout.", _wait_for_app,
               _APP + (Param("timeout_s", "float", default=10.0),
                       Param("state", default="foreground")),
               "app_lifecycle", "wait_for_app", read_only=True),
    _Operation("alert_accept", "Accept Alert", "Accept the alert or system dialog showing.",
               _alert_accept, capability="alerts", api="accept_alert"),
    _Operation("alert_dismiss", "Dismiss Alert", "Dismiss the alert or system dialog showing.",
               _alert_dismiss, capability="alerts", api="dismiss_alert"),
    _Operation("install_app", "Install App", "Install an app package from the host.",
               _install_app, (Param("path", "file_path", True),), "install",
               "mobile_extension"),
    _Operation("push_file", "Push File", "Copy a host file to the device.", _push_file,
               (Param("local_path", "file_path", True), Param("remote_path", required=True)),
               "files", "mobile_extension"),
    _Operation("pull_file", "Pull File", "Copy a device file to the host.", _pull_file,
               (Param("remote_path", required=True), Param("local_path", "file_path", True)),
               "files", "mobile_extension"),
    _Operation("get_clipboard", "Get Clipboard", "Read the device clipboard's text.",
               _get_clipboard, capability="clipboard", api="mobile_extension", read_only=True),
    _Operation("set_clipboard", "Set Clipboard", "Put text on the device clipboard.",
               _set_clipboard, (Param("text", required=True),), "clipboard",
               "mobile_extension"),
    _Operation("start_recording", "Start Screen Recording",
               "Start recording the device screen.", _start_recording,
               (Param("remote_path"), Param("time_limit_s", "int")),
               "recording", "mobile_extension"),
    _Operation("stop_recording", "Stop Screen Recording",
               "Stop recording and save the video on the host.", _stop_recording,
               (Param("local_path", "file_path", True), Param("remote_path")),
               "recording", "mobile_extension"),
)

_PLATFORM_LABELS = {PLATFORM_ANDROID: "Android", PLATFORM_IOS: "iOS"}
_SERIAL = Param("serial")
_ADB = Param("adb_path")
_URL = Param("url")
_TIMEOUT = Param("timeout_s", "float", default=5.0)
_ANDROID_SELECTOR = (Param("text"), Param("resource_id"), Param("description"),
                     Param("class_name"), _TIMEOUT, _SERIAL)
_IOS_SELECTOR = (Param("name"), Param("class_name"), Param("predicate"), _TIMEOUT, _URL)
_SWIPE = (Param("x1", "int", True), Param("y1", "int", True),
          Param("x2", "int", True), Param("y2", "int", True))


def _legacy(name: str, label: str, description: str, params: Tuple[Param, ...],
            capability: str = "input", api: str = "DeviceSession", *,
            read_only: bool = False, handwritten_mcp: bool = False) -> MobileCommand:
    platform = PLATFORM_ANDROID if name.startswith("AC_android_") else PLATFORM_IOS
    return MobileCommand(
        name, platform, f"{_PLATFORM_LABELS[platform]}: {label}", description, params,
        capability, api, read_only=read_only, legacy=True, handwritten_mcp=handwritten_mcp)


_LEGACY: Tuple[MobileCommand, ...] = (
    _legacy("AC_android_tap", "Tap", "Tap a point via adb.", _XY + (_SERIAL, _ADB), api="Tap"),
    _legacy("AC_android_swipe", "Swipe", "Swipe between two points via adb.",
            _SWIPE + (Param("duration_ms", "int", default=250), _SERIAL, _ADB), api="Swipe"),
    _legacy("AC_android_key", "Key Event", "Send a keycode (KEYCODE_HOME, BACK, a number).",
            (Param("key", required=True), _SERIAL, _ADB)),
    _legacy("AC_android_text", "Type Text",
            "Type text; ASCII via input text, otherwise a Unicode-capable path.",
            (Param("text", required=True), _SERIAL, _ADB), "unicode_text"),
    _legacy("AC_android_screenshot", "Screenshot", "Save the device screen as a PNG.",
            (Param("file_path", "file_path", True), _SERIAL, _ADB), "screenshot", "DeviceFrame"),
    _legacy("AC_android_list_devices", "List Devices", "Every device adb sees, with its state.",
            (_ADB,), api="device_setup_report", read_only=True),
    _legacy("AC_android_shell", "Shell Command", "Run an adb shell command; returns stdout.",
            (Param("command", required=True), _SERIAL, _ADB)),
    _legacy("AC_android_find_element", "Find Element",
            "Find a widget in the uiautomator2 tree; returns its bounds.", _ANDROID_SELECTOR,
            "ui_tree", read_only=True, handwritten_mcp=True),
    _legacy("AC_android_click_element", "Click Element", "Tap the first matching widget.",
            _ANDROID_SELECTOR, "ui_tree", handwritten_mcp=True),
    _legacy("AC_android_dump_hierarchy", "Dump Hierarchy", "The widget tree as XML.",
            (_SERIAL,), "ui_tree", read_only=True, handwritten_mcp=True),
    _legacy("AC_ios_tap", "Tap", "Tap a point (in points) via WebDriverAgent.",
            _XY + (_URL,), api="Tap", handwritten_mcp=True),
    _legacy("AC_ios_swipe", "Swipe", "Swipe between two points via WebDriverAgent.",
            _SWIPE + (Param("duration_s", "float", default=0.5), _URL), api="Swipe",
            handwritten_mcp=True),
    _legacy("AC_ios_type", "Type Text", "Type text into the focused field.",
            (Param("text", required=True), _URL), "unicode_text", handwritten_mcp=True),
    _legacy("AC_ios_screenshot", "Screenshot", "Save the device screen as a PNG.",
            (Param("file_path", "file_path", True), _URL), "screenshot", "DeviceFrame",
            handwritten_mcp=True),
    _legacy("AC_ios_find_element", "Find Element",
            "Find an XCUITest element; returns its bounds.", _IOS_SELECTOR, "ui_tree",
            read_only=True, handwritten_mcp=True),
    _legacy("AC_ios_click_element", "Click Element", "Tap the first matching element.",
            _IOS_SELECTOR, "ui_tree", handwritten_mcp=True),
    _legacy("AC_ios_dump_source", "Dump Source", "The XCUITest page source as XML.",
            (_URL,), "ui_tree", read_only=True, handwritten_mcp=True),
)


def _generated() -> Tuple[Tuple[MobileCommand, _Operation], ...]:
    pairs = []
    for operation in _OPERATIONS:
        for platform in operation.platforms:
            pairs.append((MobileCommand(
                f"AC_{platform}_{operation.key}", platform,
                f"{_PLATFORM_LABELS[platform]}: {operation.label}", operation.description,
                operation.params + _ADDRESS[platform], operation.capability, operation.api,
                read_only=operation.read_only), operation))
    return tuple(pairs)


_GENERATED = _generated()

#: Every mobile command: the ones that predate the table, then the generated ones.
MOBILE_COMMANDS: Tuple[MobileCommand, ...] = _LEGACY + tuple(
    command for command, _operation in _GENERATED)
_BY_NAME: Mapping[str, MobileCommand] = {command.name: command for command in MOBILE_COMMANDS}


def _annotation(param: Param) -> Any:
    """The parameter's type as the generated stub and help text should show it."""
    kind = _KINDS[param.kind]
    return kind if param.required or param.default is not None else Optional[kind]


def _signature(params: Tuple[Param, ...]) -> inspect.Signature:
    return inspect.Signature([
        inspect.Parameter(
            param.name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=inspect.Parameter.empty if param.required else param.default,
            annotation=_annotation(param))
        for param in params])


def _coerce(command: MobileCommand, param: Param, value: Any) -> Any:
    if isinstance(value, bool) and param.kind in ("int", "float"):
        raise TypeError(f"{command.name}: {param.name} must be a number, got a boolean")
    try:
        return _KINDS[param.kind](value)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{command.name}: {param.name} must be {param.kind}, got {value!r}") from error


def _bind(command: MobileCommand, signature: inspect.Signature,
          args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a call against the command's parameters: unknown and missing ones raise."""
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as error:
        raise TypeError(f"{command.name}: {error}") from error
    bound.apply_defaults()
    return {param.name: _coerce(command, param, bound.arguments[param.name])
            for param in command.params if bound.arguments[param.name] is not None}


def _handler(command: MobileCommand, operation: _Operation) -> Callable[..., Any]:
    signature = _signature(command.params)

    def handler(*args: Any, **kwargs: Any) -> Any:
        values = _bind(command, signature, args, kwargs)
        address = {name: values.pop(name, None) for name in _ADDRESS_NAMES}
        with command_session(command.platform, address["serial"] or address["url"],
                             adb_path=address["adb_path"],
                             timeout_s=address["device_timeout_s"]) as session:
            return operation.run(session, **values)

    handler.__name__ = "_ac_" + command.name[3:]
    handler.__doc__ = command.description
    # The executor, the MCP registry and help text introspect handlers.
    setattr(handler, "__signature__", signature)
    return handler


_HANDLERS: Dict[str, Callable[..., Any]] = {
    command.name: _handler(command, operation) for command, operation in _GENERATED}


def generated_handlers() -> Dict[str, Callable[..., Any]]:
    """``AC_*`` name to handler, for every command the table generates."""
    return dict(_HANDLERS)


def _executor_handler(name: str) -> Callable[..., Any]:
    """A legacy command's handler, looked up in the executor when it is called."""
    def call(**kwargs: Any) -> Any:
        from je_auto_control.utils.executor.action_executor import executor
        return executor.event_dict[name](**kwargs)
    return call


def run_mobile_command(name: str, params: Optional[Mapping[str, Any]] = None) -> Any:
    """Run one mobile command by name. Only commands in :data:`MOBILE_COMMANDS` are accepted."""
    if name not in _BY_NAME:
        raise DeviceError(f"{name!r} is not a mobile command")
    handler = _HANDLERS.get(name) or _executor_handler(name)
    return handler(**dict(params or {}))


def mcp_tool_specs() -> List[Dict[str, Any]]:
    """What the MCP registry needs to build a tool for each command that lacks one."""
    specs = []
    for command in MOBILE_COMMANDS:
        if command.handwritten_mcp or command.name in MCP_EXCLUDED:
            continue
        properties: Dict[str, Any] = {}
        for param in command.params:
            node: Dict[str, Any] = {"type": _JSON_TYPES.get(param.kind, "string")}
            if param.kind == "file_path":
                node["format"] = "path"
            if param.description:
                node["description"] = param.description
            properties[param.name] = node
        specs.append({
            "name": command.mcp_name, "description": command.description,
            "properties": properties,
            "required": [param.name for param in command.params if param.required],
            "read_only": command.read_only,
            "handler": _HANDLERS.get(command.name) or _executor_handler(command.name),
        })
    return specs


#: Desktop features with no mobile counterpart: the limit, and what to use instead.
DESKTOP_ONLY_FEATURES: Tuple[Dict[str, str], ...] = (
    {"feature": "Window management (AC_window_*, focus, move, resize, z-order)",
     "limitation": "a phone shows one app at a time; there are no windows to manage",
     "alternative": "launch_app / stop_app / app_state to choose what is in front"},
    {"feature": "Mouse buttons, wheel and hover (AC_click_mouse, AC_mouse_scroll)",
     "limitation": "touch screens have no pointer, buttons or wheel",
     "alternative": "Tap, LongPress, Swipe (to scroll), Drag and Pinch"},
    {"feature": "Keyboard shortcuts and modifier keys (AC_hotkey, AC_press_keyboard_key)",
     "limitation": "there is no physical keyboard or modifier state",
     "alternative": "type_text for text; AC_android_key / AC_ios_press_key for hardware keys"},
    {"feature": "Desktop accessibility tree (UIA, AX, AT-SPI)",
     "limitation": "those APIs describe the host's desktop, not the device",
     "alternative": "AC_android_find_element (uiautomator2) / AC_ios_find_element (XCUITest)"},
    {"feature": "COM / Office automation",
     "limitation": "COM is a Windows host API",
     "alternative": "none on the device; drive the mobile app's UI instead"},
    {"feature": "USB host passthrough and usbip",
     "limitation": "these share the host's USB devices; a phone is a USB device, not a host",
     "alternative": "none; adb and WebDriverAgent are the device transports"},
    {"feature": "Global hotkeys, triggers on host input, input recording",
     "limitation": "they observe the host's keyboard and mouse, which the device does not use",
     "alternative": "record executed mobile steps in the action journal"},
    {"feature": "Desktop screen capture and screen recording (AC_screenshot, AC_screen_record)",
     "limitation": "they capture the host's monitors",
     "alternative": "DeviceSession.capture() and the recording extension"},
)


def mobile_capability_matrix() -> Dict[str, Any]:
    """Which commands deliver each capability per platform, and what stays desktop-only."""
    rows = []
    for name in CAPABILITY_NAMES:
        row: Dict[str, Any] = {"capability": name}
        for platform in (PLATFORM_ANDROID, PLATFORM_IOS):
            row[platform] = [command.name for command in MOBILE_COMMANDS
                             if command.platform == platform and command.capability == name]
        rows.append(row)
    return {"capabilities": rows, "desktop_only": [dict(row) for row in DESKTOP_ONLY_FEATURES]}


__all__ = [
    "DESKTOP_ONLY_FEATURES", "MCP_EXCLUDED", "MOBILE_COMMANDS", "MobileCommand", "Param",
    "command_session", "device_setup_report", "generated_handlers", "mcp_tool_specs",
    "mobile_capability_matrix", "run_mobile_command",
]
