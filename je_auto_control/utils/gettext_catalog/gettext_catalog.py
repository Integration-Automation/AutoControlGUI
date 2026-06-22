"""GNU gettext catalog I/O: parse ``.po``, compile/read ``.mo``, look up messages.

The repo has ``i18n_test`` (pseudo-localisation, catalog placeholder checks) and
``message_format`` (ICU rendering) but no reader for the *de-facto* translation
format — GNU gettext ``.po`` / ``.mo``. This parses ``.po`` text (contexts,
plurals, multi-line strings, escapes, the ``Plural-Forms`` header), compiles the
binary ``.mo`` (little-endian, the format Python's own ``gettext`` reads) and
exposes ``gettext`` / ``ngettext`` / ``pgettext`` lookups.

Pure standard library (``re`` / ``struct`` / ``gettext.c2py`` for the plural
expression); imports no ``PySide6``. Parsing and compilation are pure data
in / data out, so they are fully deterministic in CI.
"""
import re
import struct
from gettext import c2py
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MO_MAGIC_LE = 0x950412DE
_MO_MAGIC_BE = 0xDE120495
_CONTEXT_SEP = "\x04"
_PLURAL_SEP = "\x00"
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}

Key = Tuple[Optional[str], str]


def _decode_escapes(text: str) -> str:
    """Decode the backslash escapes used inside ``.po`` quoted strings."""
    out: List[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            out.append(_ESCAPES.get(text[index + 1], text[index + 1]))
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


def _unquote(line: str) -> str:
    """Strip the surrounding quotes of a ``.po`` string line and unescape it."""
    stripped = line.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        stripped = stripped[1:-1]
    return _decode_escapes(stripped)


class GettextCatalog:
    """An in-memory gettext catalog with ``.po`` / ``.mo`` round-tripping."""

    def __init__(self) -> None:
        self._messages: Dict[Key, List[str]] = {}
        self._plural_ids: Dict[Key, str] = {}
        self.metadata: Dict[str, str] = {}
        self.nplurals = 2
        self._plural_func = c2py("n != 1")

    # -- building ----------------------------------------------------------

    def add(self, msgid: str, message: object = "", *,
            context: Optional[str] = None,
            plural_id: Optional[str] = None) -> None:
        """Add a message; ``message`` is a string, or a list of plural forms
        (pair with ``plural_id``)."""
        key = (context, msgid)
        self._messages[key] = (list(message) if isinstance(message, list)
                               else [str(message)])
        if plural_id is not None:
            self._plural_ids[key] = plural_id

    def finalize(self) -> None:
        """Parse the header entry for ``Plural-Forms`` / metadata."""
        header = self._messages.get((None, ""))
        if not header:
            return
        for raw in header[0].split("\n"):
            if ":" in raw:
                name, value = raw.split(":", 1)
                self.metadata[name.strip()] = value.strip()
        self._apply_plural_forms(self.metadata.get("Plural-Forms", ""))

    def _apply_plural_forms(self, spec: str) -> None:
        count = re.search(r"nplurals\s*=\s*(\d+)", spec)
        if count:
            self.nplurals = int(count.group(1))
        expr = re.search(r"plural\s*=\s*([^;]+)", spec)
        if expr:
            try:
                self._plural_func = c2py(expr.group(1).strip())
            except ValueError:
                pass

    # -- lookup ------------------------------------------------------------

    def gettext(self, msgid: str, *, context: Optional[str] = None) -> str:
        """Return the translation of ``msgid`` (or ``msgid`` if untranslated)."""
        forms = self._messages.get((context, msgid))
        if forms and forms[0]:
            return forms[0]
        return msgid

    def ngettext(self, msgid: str, msgid_plural: str, n: int, *,
                 context: Optional[str] = None) -> str:
        """Return the plural-correct translation for count ``n``."""
        forms = self._messages.get((context, msgid))
        if forms:
            index = self._plural_func(n)
            if 0 <= index < len(forms) and forms[index]:
                return forms[index]
        return msgid if n == 1 else msgid_plural

    def pgettext(self, context: str, msgid: str) -> str:
        """Context-qualified :meth:`gettext`."""
        return self.gettext(msgid, context=context)

    # -- .mo output --------------------------------------------------------

    def _mo_pairs(self) -> List[Tuple[bytes, bytes]]:
        pairs: List[Tuple[bytes, bytes]] = []
        for (context, msgid), forms in self._messages.items():
            original = msgid
            plural_id = self._plural_ids.get((context, msgid))
            if plural_id is not None:
                original = msgid + _PLURAL_SEP + plural_id
            if context is not None:
                original = context + _CONTEXT_SEP + original
            pairs.append((original.encode("utf-8"),
                          _PLURAL_SEP.join(forms).encode("utf-8")))
        pairs.sort(key=lambda pair: pair[0])
        return pairs

    def to_mo_bytes(self) -> bytes:
        """Serialise the catalog to GNU ``.mo`` binary bytes (little-endian)."""
        return _pack_mo(self._mo_pairs())

    def compile_mo(self, path: str) -> str:
        """Write the catalog as a ``.mo`` file; return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(self.to_mo_bytes())
        return str(out)


def _pack_mo(pairs: List[Tuple[bytes, bytes]]) -> bytes:
    """Pack sorted (original, translation) byte pairs into ``.mo`` format."""
    count = len(pairs)
    originals_table = 7 * 4
    translations_table = originals_table + 8 * count
    offset = translations_table + 8 * count
    originals: List[Tuple[int, int]] = []
    translations: List[Tuple[int, int]] = []
    blob = bytearray()
    for original, _ in pairs:
        originals.append((len(original), offset))
        blob += original + b"\x00"
        offset += len(original) + 1
    for _, translation in pairs:
        translations.append((len(translation), offset))
        blob += translation + b"\x00"
        offset += len(translation) + 1
    header = struct.pack("<7I", _MO_MAGIC_LE, 0, count,
                         originals_table, translations_table, 0, 0)
    table = b"".join(struct.pack("<2I", length, off)
                     for length, off in originals + translations)
    return header + table + bytes(blob)


def _store_mo_entry(catalog: GettextCatalog, original: str,
                    translation: str) -> None:
    context: Optional[str] = None
    if _CONTEXT_SEP in original:
        context, original = original.split(_CONTEXT_SEP, 1)
    ids = original.split(_PLURAL_SEP)
    forms = translation.split(_PLURAL_SEP)
    if len(ids) > 1:
        catalog.add(ids[0], forms, context=context, plural_id=ids[1])
    else:
        catalog.add(ids[0], forms[0], context=context)


def read_mo(data: bytes) -> GettextCatalog:
    """Parse GNU ``.mo`` binary ``data`` into a catalog."""
    magic = struct.unpack("<I", data[:4])[0]
    if magic not in (_MO_MAGIC_LE, _MO_MAGIC_BE):
        raise ValueError("not a .mo file (bad magic)")
    endian = "<" if magic == _MO_MAGIC_LE else ">"
    count, orig_off, trans_off = struct.unpack(endian + "III", data[8:20])
    catalog = GettextCatalog()
    for index in range(count):
        olen, ostart = struct.unpack(
            endian + "II", data[orig_off + 8 * index:orig_off + 8 * index + 8])
        tlen, tstart = struct.unpack(
            endian + "II", data[trans_off + 8 * index:trans_off + 8 * index + 8])
        original = data[ostart:ostart + olen].decode("utf-8")
        translation = data[tstart:tstart + tlen].decode("utf-8")
        _store_mo_entry(catalog, original, translation)
    catalog.finalize()
    return catalog


def read_mo_file(path: str) -> GettextCatalog:
    """Read a ``.mo`` file into a catalog."""
    return read_mo(Path(path).read_bytes())


# --- .po parsing ----------------------------------------------------------

def _append(entry: Dict[str, object], field: Optional[object],
            value: str) -> None:
    """Append a continuation string to the field last seen in a block."""
    if field == "msgctxt":
        entry["msgctxt"] = str(entry.get("msgctxt", "")) + value
    elif field == "msgid":
        entry["msgid"] = str(entry.get("msgid", "")) + value
    elif field == "msgid_plural":
        entry["msgid_plural"] = str(entry.get("msgid_plural", "")) + value
    elif isinstance(field, int):
        plurals: Dict[int, str] = entry.setdefault("plurals", {})  # type: ignore[assignment]
        plurals[field] = plurals.get(field, "") + value


def _parse_block(block: str) -> Optional[Dict[str, object]]:
    """Parse one blank-line-delimited ``.po`` block into a field dict."""
    entry: Dict[str, object] = {}
    field: Optional[object] = None
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        field = _consume_line(stripped, entry, field)
    return entry if "msgid" in entry else None


def _consume_line(stripped: str, entry: Dict[str, object],
                  field: Optional[object]) -> Optional[object]:
    """Process one ``.po`` line, returning the field it continues."""
    plural = re.match(r"msgstr\[(\d+)\]\s*(.*)", stripped)
    if plural:
        field = int(plural.group(1))
        _append(entry, field, _unquote(plural.group(2)))
    elif stripped.startswith("msgctxt "):
        field = "msgctxt"
        _append(entry, field, _unquote(stripped[8:]))
    elif stripped.startswith("msgid_plural "):
        field = "msgid_plural"
        _append(entry, field, _unquote(stripped[13:]))
    elif stripped.startswith("msgid "):
        field = "msgid"
        _append(entry, field, _unquote(stripped[6:]))
    elif stripped.startswith("msgstr "):
        field = 0
        _append(entry, field, _unquote(stripped[7:]))
    elif stripped.startswith('"'):
        _append(entry, field, _unquote(stripped))
    return field


def _store_block(catalog: GettextCatalog, entry: Dict[str, object]) -> None:
    context = entry.get("msgctxt")
    ctx = None if context is None else str(context)
    msgid = str(entry["msgid"])
    plurals: Dict[int, str] = entry.get("plurals", {})  # type: ignore[assignment]
    if "msgid_plural" in entry:
        forms = [plurals[i] for i in sorted(plurals)] if plurals else [""]
        catalog.add(msgid, forms, context=ctx,
                    plural_id=str(entry["msgid_plural"]))
    else:
        catalog.add(msgid, plurals.get(0, ""), context=ctx)


def parse_po(text: str) -> GettextCatalog:
    """Parse ``.po`` source ``text`` into a :class:`GettextCatalog`."""
    catalog = GettextCatalog()
    for block in re.split(r"\n[ \t]*\n", text or ""):
        entry = _parse_block(block)
        if entry is not None:
            _store_block(catalog, entry)
    catalog.finalize()
    return catalog


def parse_po_file(path: str) -> GettextCatalog:
    """Read and parse a ``.po`` file into a catalog."""
    return parse_po(Path(path).read_text(encoding="utf-8"))
