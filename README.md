# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** is a cross-platform Python GUI automation framework providing mouse control, keyboard input, image recognition, screen capture, action scripting, and report generation — all through a unified API that works on Windows, macOS, and Linux (X11).

**[繁體中文](README/README_zh-TW.md)** | **[简体中文](README/README_zh-CN.md)**

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
  - [Mouse Control](#mouse-control)
  - [Keyboard Control](#keyboard-control)
  - [Image Recognition](#image-recognition)
  - [Screen Operations](#screen-operations)
  - [Action Recording & Playback](#action-recording--playback)
  - [Action Scripting (JSON Executor)](#action-scripting-json-executor)
  - [Report Generation](#report-generation)
  - [Remote Automation (Socket Server)](#remote-automation-socket-server)
  - [Shell Command Execution](#shell-command-execution)
  - [Screen Recording](#screen-recording)
  - [Callback Executor](#callback-executor)
  - [Package Manager](#package-manager)
  - [Project Management](#project-management)
  - [Window Management](#window-management)
  - [GUI Application](#gui-application)
- [Command-Line Interface](#command-line-interface)
- [Platform Support](#platform-support)
- [Development](#development)
- [License](#license)

---

## Features

- **Mouse Automation** — move, click, press, release, drag, and scroll with precise coordinate control
- **Keyboard Automation** — press/release individual keys, type strings, hotkey combinations, key state detection
- **Image Recognition** — locate UI elements on screen using OpenCV template matching with configurable threshold
- **Screenshot & Screen Recording** — capture full screen or regions as images, record screen to video (AVI/MP4)
- **Action Recording & Playback** — record mouse/keyboard events and replay them
- **JSON-Based Action Scripting** — define and execute automation flows using JSON action files
- **Report Generation** — export test records as HTML, JSON, or XML reports with success/failure status
- **Remote Automation** — start a TCP socket server to receive and execute automation commands from remote clients
- **Shell Integration** — execute shell commands within automation workflows with async output capture
- **Callback Executor** — trigger automation functions with callback hooks for chaining operations
- **Dynamic Package Loading** — extend the executor at runtime by importing external Python packages
- **Project & Template Management** — scaffold automation projects with keyword/executor directory structure
- **Window Management** — send keyboard/mouse events directly to specific windows (Windows/Linux)
- **GUI Application** — built-in PySide6 graphical interface for interactive automation
- **Cross-Platform** — unified API across Windows, macOS, and Linux (X11)

---

## Architecture

```
je_auto_control/
├── wrapper/                    # Platform-agnostic API layer
│   ├── platform_wrapper.py     # Auto-detects OS and loads the correct backend
│   ├── auto_control_mouse.py   # Mouse operations
│   ├── auto_control_keyboard.py# Keyboard operations
│   ├── auto_control_image.py   # Image recognition (OpenCV template matching)
│   ├── auto_control_screen.py  # Screenshot, screen size, pixel color
│   └── auto_control_record.py  # Action recording/playback
├── windows/                    # Windows-specific backend (Win32 API / ctypes)
├── osx/                        # macOS-specific backend (pyobjc / Quartz)
├── linux_with_x11/             # Linux-specific backend (python-Xlib)
├── gui/                        # PySide6 GUI application
└── utils/
    ├── executor/               # JSON action executor engine
    ├── callback/               # Callback function executor
    ├── cv2_utils/              # OpenCV screenshot, template matching, video recording
    ├── socket_server/          # TCP socket server for remote automation
    ├── shell_process/          # Shell command manager
    ├── generate_report/        # HTML / JSON / XML report generators
    ├── test_record/            # Test action recording
    ├── json/                   # JSON action file read/write
    ├── project/                # Project scaffolding & templates
    ├── package_manager/        # Dynamic package loading
    ├── logging/                # Logging
    └── exception/              # Custom exception classes
```

The `platform_wrapper.py` module automatically detects the current operating system and imports the corresponding backend, so all wrapper functions work identically regardless of platform.

---

## Installation

### Basic Installation

```bash
pip install je_auto_control
```

### With GUI Support (PySide6)

```bash
pip install je_auto_control[gui]
```

### Linux Prerequisites

On Linux, install the following system packages before installing:

```bash
sudo apt-get install cmake libssl-dev
```

---

## Requirements

- **Python** >= 3.10
- **pip** >= 19.3

### Dependencies

| Package | Purpose |
|---|---|
| `je_open_cv` | Image recognition (OpenCV template matching) |
| `pillow` | Screenshot capture |
| `mss` | Fast multi-monitor screenshot |
| `pyobjc` | macOS backend (auto-installed on macOS) |
| `python-Xlib` | Linux X11 backend (auto-installed on Linux) |
| `PySide6` | GUI application (optional, install with `[gui]`) |
| `qt-material` | GUI theme (optional, install with `[gui]`) |

---

## Quick Start

### Mouse Control

```python
import je_auto_control

# Get current mouse position
x, y = je_auto_control.get_mouse_position()
print(f"Mouse at: ({x}, {y})")

# Move mouse to coordinates
je_auto_control.set_mouse_position(500, 300)

# Left click at current position (use key name)
je_auto_control.click_mouse("mouse_left")

# Right click at specific coordinates
je_auto_control.click_mouse("mouse_right", x=800, y=400)

# Scroll down
je_auto_control.mouse_scroll(scroll_value=5)
```

### Keyboard Control

```python
import je_auto_control

# Press and release a single key
je_auto_control.type_keyboard("a")

# Type a whole string character by character
je_auto_control.write("Hello World")

# Hotkey combination (e.g., Ctrl+C)
je_auto_control.hotkey(["ctrl_l", "c"])

# Check if a key is currently pressed
is_pressed = je_auto_control.check_key_is_press("shift_l")
```

### Image Recognition

```python
import je_auto_control

# Find all occurrences of an image on screen
positions = je_auto_control.locate_all_image("button.png", detect_threshold=0.9)
# Returns: [[x1, y1, x2, y2], ...]

# Find a single image and get its center coordinates
cx, cy = je_auto_control.locate_image_center("icon.png", detect_threshold=0.85)
print(f"Found at: ({cx}, {cy})")

# Find an image and automatically click it
je_auto_control.locate_and_click("submit_button.png", mouse_keycode="mouse_left")
```

### Screenshot

```python
import je_auto_control

# Take a full-screen screenshot and save to file
je_auto_control.pil_screenshot("screenshot.png")

# Take a screenshot of a specific region [x1, y1, x2, y2]
je_auto_control.pil_screenshot("region.png", screen_region=[100, 100, 500, 400])

# Get screen resolution
width, height = je_auto_control.screen_size()

# Get pixel color at coordinates
color = je_auto_control.get_pixel(500, 300)
```

### Action Recording & Playback

```python
import je_auto_control
import time

# Start recording mouse and keyboard events
je_auto_control.record()

time.sleep(10)  # Record for 10 seconds

# Stop recording and get the action list
actions = je_auto_control.stop_record()

# Replay the recorded actions
je_auto_control.execute_action(actions)
```

### JSON Action Scripting

Create a JSON action file (`actions.json`):

```json
[
    ["AC_set_mouse_position", {"x": 500, "y": 300}],
    ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "Hello from AutoControl"}],
    ["AC_screenshot", {"file_path": "result.png"}],
    ["AC_hotkey", {"key_code_list": ["ctrl_l", "s"]}]
]
```

Execute it:

```python
import je_auto_control

# Execute from file
je_auto_control.execute_action(je_auto_control.read_action_json("actions.json"))

# Or execute from a list directly
je_auto_control.execute_action([
    ["AC_set_mouse_position", {"x": 100, "y": 200}],
    ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
])
```

**Available action commands:**

| Category | Commands |
|---|---|
| Mouse | `AC_click_mouse`, `AC_set_mouse_position`, `AC_get_mouse_position`, `AC_press_mouse`, `AC_release_mouse`, `AC_mouse_scroll`, `AC_mouse_left`, `AC_mouse_right`, `AC_mouse_middle` |
| Keyboard | `AC_type_keyboard`, `AC_press_keyboard_key`, `AC_release_keyboard_key`, `AC_write`, `AC_hotkey`, `AC_check_key_is_press` |
| Image | `AC_locate_all_image`, `AC_locate_image_center`, `AC_locate_and_click` |
| Screen | `AC_screen_size`, `AC_screenshot` |
| Record | `AC_record`, `AC_stop_record` |
| Report | `AC_generate_html`, `AC_generate_json`, `AC_generate_xml`, `AC_generate_html_report`, `AC_generate_json_report`, `AC_generate_xml_report` |
| Project | `AC_create_project` |
| Shell | `AC_shell_command` |
| Process | `AC_execute_process` |
| Executor | `AC_execute_action`, `AC_execute_files` |

### Report Generation

```python
import je_auto_control

# Enable test recording first
je_auto_control.test_record_instance.set_record_enable(True)

# ... perform automation actions ...
je_auto_control.set_mouse_position(100, 200)
je_auto_control.click_mouse("mouse_left")

# Generate reports
je_auto_control.generate_html_report("test_report")   # -> test_report.html
je_auto_control.generate_json_report("test_report")   # -> test_report.json
je_auto_control.generate_xml_report("test_report")    # -> test_report.xml

# Or get report content as string
html_string = je_auto_control.generate_html()
json_string = je_auto_control.generate_json()
xml_string = je_auto_control.generate_xml()
```

Reports include: function name, parameters, timestamp, and exception info (if any) for each recorded action. HTML reports display successful actions in cyan and failed actions in red.

### Remote Automation (Socket Server)

Start a TCP server to receive JSON automation commands from remote clients:

```python
import je_auto_control

# Start the server (default: localhost:9938)
server = je_auto_control.start_autocontrol_socket_server(host="localhost", port=9938)

# The server runs in a background thread
# Send JSON action commands via TCP to execute remotely
# Send "quit_server" to shut down
```

Client example:

```python
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("localhost", 9938))

# Send an automation command
command = json.dumps([
    ["AC_set_mouse_position", {"x": 500, "y": 300}],
    ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
])
sock.sendall(command.encode("utf-8"))

# Receive response
response = sock.recv(8192).decode("utf-8")
print(response)
sock.close()
```

### Shell Command Execution

```python
import je_auto_control

# Using the default shell manager
je_auto_control.default_shell_manager.exec_shell("echo Hello")
je_auto_control.default_shell_manager.pull_text()  # Print captured output

# Or create a custom ShellManager
shell = je_auto_control.ShellManager(shell_encoding="utf-8")
shell.exec_shell("ls -la")
shell.pull_text()
shell.exit_program()
```

### Screen Recording

```python
import je_auto_control
import time

# Method 1: ScreenRecorder (manages multiple recordings)
recorder = je_auto_control.ScreenRecorder()
recorder.start_new_record(
    recorder_name="my_recording",
    path_and_filename="output.avi",
    codec="XVID",
    frame_per_sec=30,
    resolution=(1920, 1080)
)
time.sleep(10)
recorder.stop_record("my_recording")

# Method 2: RecordingThread (simple single recording, outputs MP4)
recording = je_auto_control.RecordingThread(video_name="my_video", fps=20)
recording.start()
time.sleep(10)
recording.stop()
```

### Callback Executor

Execute an automation function and trigger a callback upon completion:

```python
import je_auto_control

def my_callback():
    print("Action completed!")

# Execute set_mouse_position then call my_callback
je_auto_control.callback_executor.callback_function(
    trigger_function_name="AC_set_mouse_position",
    callback_function=my_callback,
    x=500, y=300
)

# With callback parameters
def on_done(message):
    print(f"Done: {message}")

je_auto_control.callback_executor.callback_function(
    trigger_function_name="AC_click_mouse",
    callback_function=on_done,
    callback_function_param={"message": "Click finished"},
    callback_param_method="kwargs",
    mouse_keycode="mouse_left"
)
```

### Package Manager

Dynamically load external Python packages into the executor at runtime:

```python
import je_auto_control

# Add all functions/classes from a package to the executor
je_auto_control.package_manager.add_package_to_executor("os")

# Now you can use os functions in JSON action scripts:
# ["os_getcwd", {}]
# ["os_listdir", {"path": "."}]
```

### Project Management

Scaffold a project directory structure with template files:

```python
import je_auto_control

# Create a project structure
je_auto_control.create_project_dir(project_path="./my_project", parent_name="AutoControl")

# This creates:
# my_project/
# └── AutoControl/
#     ├── keyword/
#     │   ├── keyword1.json        # Template action file
#     │   ├── keyword2.json        # Template action file
#     │   └── bad_keyword_1.json   # Error handling template
#     └── executor/
#         ├── executor_one_file.py  # Execute single file example
#         ├── executor_folder.py    # Execute folder example
#         └── executor_bad_file.py  # Error handling example
```

### Window Management

Send events directly to specific windows (Windows and Linux only):

```python
import je_auto_control

# Send keyboard event to a window by title
je_auto_control.send_key_event_to_window("Notepad", keycode="a")

# Send mouse event to a window handle
je_auto_control.send_mouse_event_to_window(window_handle, mouse_keycode="mouse_left", x=100, y=50)
```

### GUI Application

Launch the built-in graphical interface (requires `[gui]` extra):

```python
import je_auto_control
je_auto_control.start_autocontrol_gui()
```

Or from the command line:

```bash
python -m je_auto_control
```

---

## Command-Line Interface

AutoControl can be used directly from the command line:

```bash
# Execute a single action file
python -m je_auto_control -e actions.json

# Execute all action files in a directory
python -m je_auto_control -d ./action_files/

# Execute a JSON string directly
python -m je_auto_control --execute_str '[["AC_screenshot", {"file_path": "test.png"}]]'

# Create a project template
python -m je_auto_control -c ./my_project
```

---

## Platform Support

| Platform | Status | Backend | Notes |
|---|---|---|---|
| Windows 10 / 11 | Supported | Win32 API (ctypes) | Full feature support |
| macOS 10.15+ | Supported | pyobjc / Quartz | Action recording not available; `send_key_event_to_window` / `send_mouse_event_to_window` not supported |
| Linux (X11) | Supported | python-Xlib | Full feature support |
| Linux (Wayland) | Not supported | — | May be added in a future release |
| Raspberry Pi 3B / 4B | Supported | python-Xlib | Runs on X11 |

---

## Development

### Setting Up

```bash
git clone https://github.com/Intergration-Automation-Testing/AutoControl.git
cd AutoControl
pip install -r dev_requirements.txt
```

### Running Tests

```bash
# Unit tests
python -m pytest test/unit_test/

# Integration tests
python -m pytest test/integrated_test/
```

### Project Links

- **Homepage**: https://github.com/Intergration-Automation-Testing/AutoControl
- **Documentation**: https://autocontrol.readthedocs.io/en/latest/
- **PyPI**: https://pypi.org/project/je_auto_control/

---

## License

[MIT License](LICENSE) © JE-Chen
