"""Tesseract engine discovery, configuration and health checks.

The OCR calls (``find_text_matches`` and friends) only *run* the engine. These
helpers answer what a host needs to know before the first call -- where the
executable is, which language data is installed, whether the engine runs at
all -- so the host never imports ``pytesseract`` itself or writes its module
globals behind this package's back. The engine command still has exactly one
writer, :meth:`TesseractBackend.set_cmd` (``set_tesseract_cmd``).

Typical start-up, for an engine that may not be on ``PATH``::

    command = find_tesseract_cmd()
    if command:
        set_tesseract_cmd(command)
    ok, reason = ocr_status()

Imports no ``PySide6``.
"""
import os
import shutil
from typing import List, NamedTuple, Optional

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError
from je_auto_control.utils.ocr.backends.tesseract_backend import TesseractBackend
from je_auto_control.utils.platform_id import is_macos, is_windows

#: Environment variable naming the engine executable; read by
#: :func:`find_tesseract_cmd` before ``PATH``.
TESSERACT_CMD_ENV = "TESSERACT_CMD"
#: Environment variable the engine reads for its language-data directory.
TESSDATA_ENV = "TESSDATA_PREFIX"

#: :func:`ocr_status` reasons. Stable strings, safe to branch on.
OCR_READY = "ready"
OCR_MISSING_PACKAGE = "missing_package"
OCR_MISSING_ENGINE = "missing_engine"
OCR_ENGINE_UNUSABLE = "engine_unusable"
OCR_NO_LANGUAGE_DATA = "no_language_data"

#: Where the installers put the engine when they do not add it to ``PATH``
#: (the Windows installer does not by default).
_MACOS_CANDIDATES = ("/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract",
                     "/opt/local/bin/tesseract")
_UNIX_CANDIDATES = ("/usr/bin/tesseract", "/usr/local/bin/tesseract")


class OCRStatus(NamedTuple):
    """Whether OCR can work here, and if not, which part is missing.

    ``reason`` is one of the ``OCR_*`` constants in this module.
    """
    ok: bool
    reason: str


def _windows_candidates() -> List[str]:
    roots = [os.environ.get("ProgramFiles") or r"C:\Program Files",
             os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "Programs"))
    return [os.path.join(root, "Tesseract-OCR", "tesseract.exe") for root in roots]


def _install_candidates(platform: str = "") -> List[str]:
    """Conventional install locations for ``platform`` (default: this one)."""
    if is_windows(platform):
        return _windows_candidates()
    if is_macos(platform):
        return list(_MACOS_CANDIDATES)
    return list(_UNIX_CANDIDATES)


def find_tesseract_cmd() -> Optional[str]:
    """Return the absolute path of the Tesseract executable, or ``None``.

    Looks in order at ``$TESSERACT_CMD`` (when it names an existing file),
    ``PATH``, then the installers' conventional locations. Only looks:
    pass the result to ``set_tesseract_cmd`` to make OCR use it.
    """
    override = os.environ.get(TESSERACT_CMD_ENV, "").strip()
    if override:
        if os.path.isfile(override):
            return os.path.abspath(override)
        autocontrol_logger.warning(
            "%s names no file (%r); searching PATH instead", TESSERACT_CMD_ENV, override)
    found = shutil.which("tesseract")
    if found:
        return os.path.abspath(found)
    for candidate in _install_candidates():
        if os.path.isfile(candidate):
            return candidate
    return None


def set_tessdata_dir(path: str | os.PathLike[str] | None) -> str | None:
    """Point the engine at the directory holding ``*.traineddata``; return it resolved.

    Sets ``$TESSDATA_PREFIX`` for this process, which every later engine run
    inherits, so it also changes what :func:`ocr_languages` reports. ``None``
    removes the variable and the engine falls back to its built-in location.
    Raises ``AutoControlActionException`` when ``path`` is not an existing
    directory; an empty directory is accepted (``ocr_status`` then reports
    ``no_language_data``).
    """
    if path is None:
        os.environ.pop(TESSDATA_ENV, None)
        return None
    resolved = os.path.realpath(os.fspath(path))
    if not os.path.isdir(resolved):
        raise AutoControlActionException(f"tessdata directory does not exist: {resolved}")
    os.environ[TESSDATA_ENV] = resolved
    return resolved


def ocr_languages() -> Optional[List[str]]:
    """Return the installed Tesseract language codes, sorted, or ``None``.

    ``None`` and ``[]`` mean different things and call for opposite handling:

    * ``[]`` -- the engine answered and has **no language data**, so every OCR
      call will fail;
    * ``None`` -- the engine **could not be asked** (``pytesseract`` or the
      executable is missing, or listing failed), so nothing is known about
      the languages.

    Asked afresh on every call, never cached.
    """
    try:
        return TesseractBackend().languages()
    except OCRBackendNotAvailableError as error:
        autocontrol_logger.info("ocr_languages: the engine cannot be asked: %r", error)
        return None


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None or os.path.isfile(command)


def ocr_status() -> OCRStatus:
    """Report whether Tesseract OCR can work here: ``(ok, reason)``.

    Checks, in order, and stops at the first missing part: the ``pytesseract``
    package (``missing_package``), the configured engine command
    (``missing_engine``), running it (``engine_unusable``), and its language
    data (``no_language_data``, only when the engine *answered* with an empty
    list). Otherwise ``(True, "ready")``. It checks the command OCR would use
    and configures nothing; see the module docstring for the start-up recipe.
    """
    backend = TesseractBackend()
    try:
        command = backend.cmd
    except OCRBackendNotAvailableError:
        return OCRStatus(False, OCR_MISSING_PACKAGE)
    if not _command_exists(command):
        return OCRStatus(False, OCR_MISSING_ENGINE)
    try:
        backend.version()
    except OCRBackendNotAvailableError as error:
        autocontrol_logger.warning("ocr_status: the engine does not run: %r", error)
        return OCRStatus(False, OCR_ENGINE_UNUSABLE)
    languages = ocr_languages()
    if languages is not None and not languages:
        return OCRStatus(False, OCR_NO_LANGUAGE_DATA)
    return OCRStatus(True, OCR_READY)


__all__ = [
    "OCRStatus", "OCR_ENGINE_UNUSABLE", "OCR_MISSING_ENGINE",
    "OCR_MISSING_PACKAGE", "OCR_NO_LANGUAGE_DATA", "OCR_READY",
    "TESSDATA_ENV", "TESSERACT_CMD_ENV",
    "find_tesseract_cmd", "ocr_languages", "ocr_status", "set_tessdata_dir",
]
