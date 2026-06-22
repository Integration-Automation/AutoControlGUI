"""Generate an A2A (agent-to-agent) Agent Card for AutoControl.

The A2A protocol (https://a2a-protocol.org) lets agents discover each
other through an *Agent Card* — a JSON document advertising the agent's
identity, endpoint, and skills. Publishing one lets other agents call
AutoControl as a GUI-automation peer (typically served at
``/.well-known/agent-card.json``).

Pure standard library; imports no ``PySide6``. The package version is read
from installed metadata with a pinned fallback.
"""
import json
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List

_PYPI_NAME = "je_auto_control"
_DEFAULT_VERSION = "0.0.189"
_DEFAULT_NAME = "AutoControl"
_DEFAULT_URL = "http://127.0.0.1:9999/"
_DESCRIPTION = (
    "Cross-platform GUI automation peer: mouse/keyboard control, image and "
    "OCR recognition, native-UI (accessibility) control, and action "
    "scripting.")

# (id, name, description, tags) for each advertised high-level skill.
_SKILLS = [
    ("gui-input", "GUI Input Control",
     "Move/click the mouse and type/press keys on the desktop.",
     ["mouse", "keyboard", "input"]),
    ("screen-vision", "Screen Vision",
     "Capture the screen and locate elements by image template or OCR text.",
     ["screenshot", "image", "ocr", "vision"]),
    ("native-ui", "Native UI Control",
     "Read and drive native controls through the accessibility tree.",
     ["accessibility", "uia", "native"]),
    ("window-management", "Window Management",
     "List, focus, move, resize, and tile application windows.",
     ["windows", "focus", "layout"]),
    ("automation-scripting", "Automation Scripting",
     "Run recorded JSON action flows with variables and flow control.",
     ["scripting", "replay", "flow"]),
]


def _package_version() -> str:
    try:
        return metadata.version(_PYPI_NAME)
    except metadata.PackageNotFoundError:
        return _DEFAULT_VERSION


def _skills() -> List[Dict[str, Any]]:
    return [{"id": skill_id, "name": name, "description": description,
             "tags": list(tags)}
            for skill_id, name, description, tags in _SKILLS]


def build_agent_card(*, name: str = _DEFAULT_NAME, url: str = _DEFAULT_URL,
                     version: str = "",
                     description: str = _DESCRIPTION) -> Dict[str, Any]:
    """Return an A2A Agent Card describing this AutoControl instance."""
    return {
        "protocolVersion": "0.3.0",
        "name": name,
        "description": description,
        "url": url,
        "version": version or _package_version(),
        "preferredTransport": "JSONRPC",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": _skills(),
    }


def write_agent_card(path: str = "agent-card.json",
                     **kwargs: Any) -> str:
    """Write an Agent Card to ``path``; return the resolved path.

    Keyword arguments are forwarded to :func:`build_agent_card`.
    """
    card = build_agent_card(**kwargs)
    target = Path(path)
    target.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    return str(target.resolve())
