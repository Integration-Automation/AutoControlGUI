# Third-Party Licenses

AutoControl is distributed under the [MIT License](LICENSE). It depends on
the third-party components listed below, each covered by its own license.
Full copies of the upstream license texts are archived under `LICENSEs/`.

---

## Runtime dependencies (pinned in `pyproject.toml`)

| Package | Version | License | Purpose |
|---|---|---|---|
| [je_open_cv](https://pypi.org/project/je-open-cv/) | 0.0.22 | MIT | OpenCV-based image recognition helpers (`locate_all_image`, template match) |
| [Pillow](https://pypi.org/project/Pillow/) | 12.2.0 | MIT-CMU (HPND) | Screenshot encoding, image I/O |
| [mss](https://pypi.org/project/mss/) | 10.1.0 | MIT | Fast multi-monitor screenshot backend |
| [pyobjc-core](https://pypi.org/project/pyobjc-core/) | 12.1 | MIT | macOS backend — Python/Objective-C bridge *(Darwin only)* |
| [pyobjc](https://pypi.org/project/pyobjc/) | 12.1 | MIT | macOS backend — Cocoa / Quartz bindings *(Darwin only)* |
| [python-Xlib](https://pypi.org/project/python-xlib/) | 0.33 | LGPL-2.1-or-later | Linux X11 backend *(Linux only)* |

### Optional GUI extras (`pip install je_auto_control[gui]`)

| Package | Version | License | Purpose |
|---|---|---|---|
| [PySide6](https://pypi.org/project/PySide6/) | 6.11.0 | LGPL-3.0 / Qt Commercial | Qt 6 GUI framework used by `start_autocontrol_gui()` |
| [qt-material](https://pypi.org/project/qt-material/) | 2.17 | BSD-2-Clause | Material Design themes for PySide6 |

### Optional feature dependencies (loaded lazily, not pinned)

| Package | License | Purpose |
|---|---|---|
| [pytesseract](https://pypi.org/project/pytesseract/) + Tesseract OCR | Apache-2.0 / Apache-2.0 | OCR engine behind `find_text_matches`, `click_text` |
| [anthropic](https://pypi.org/project/anthropic/) | MIT | VLM element locator — Anthropic backend (`locate_by_description`) |
| [openai](https://pypi.org/project/openai/) | Apache-2.0 | VLM element locator — OpenAI backend |
| [uiautomation](https://pypi.org/project/uiautomation/) | Apache-2.0 | Windows accessibility backend (UIA) *(Windows only)* |

These are imported on first use; AutoControl degrades gracefully when any
are absent (see `VLMNotAvailableError`, `AccessibilityNotAvailableError`,
and the OCR engine's `pytesseract is required` error message).

---

## Development-only dependencies

Listed in `dev_requirements.txt`. Build/packaging and documentation only —
not shipped with the wheel.

| Package | License |
|---|---|
| [wheel](https://pypi.org/project/wheel/) | MIT |
| [build](https://pypi.org/project/build/) | MIT |
| [twine](https://pypi.org/project/twine/) | Apache-2.0 |
| [sphinx](https://pypi.org/project/Sphinx/) | BSD-2-Clause |
| [sphinx-rtd-theme](https://pypi.org/project/sphinx-rtd-theme/) | MIT |
| [pytest](https://pypi.org/project/pytest/) | MIT |
| [ruff](https://pypi.org/project/ruff/) | MIT |
| [pylint](https://pypi.org/project/pylint/) | GPL-2.0 |
| [bandit](https://pypi.org/project/bandit/) | Apache-2.0 |
| [radon](https://pypi.org/project/radon/) | MIT |

---

## External runtime services

Optional backends AutoControl talks to over HTTPS. API keys are read only
from environment variables and never logged or persisted.

| Service | Used by | Env var | Terms |
|---|---|---|---|
| Anthropic API | VLM locator | `ANTHROPIC_API_KEY` | https://www.anthropic.com/legal |
| OpenAI API | VLM locator | `OPENAI_API_KEY` | https://openai.com/policies |

Override the preferred backend with `AUTOCONTROL_VLM_BACKEND=anthropic|openai`
and the default model with `AUTOCONTROL_VLM_MODEL=<model-id>`.

---

## Attributions

Local copies of upstream license texts are kept under `LICENSEs/` for:

- `AutoControl/LICENSE` — this project's MIT license
- `Numpy/` — NumPy (transitive via OpenCV)
- `OpenCV/` — OpenCV (transitive via `je_open_cv`)
- `Pillow/` — Pillow
- `python_xlib/` — python-Xlib

If you redistribute AutoControl, include these notices alongside your
distribution and comply with each dependency's license terms (in
particular LGPL components — PySide6 and python-Xlib — require that users
can relink against modified versions of the library).
