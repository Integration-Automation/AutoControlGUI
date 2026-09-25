"""Build and parse ``multipart/form-data`` bodies (file upload support).

``http_request`` sends only JSON or raw bodies — there was no file upload, and
the stdlib ``cgi`` module (which once parsed multipart) was removed in Python
3.13. This assembles a ``multipart/form-data`` body from text fields and files
with a deterministic boundary, and parses one back.

Pure standard library (``re`` / ``secrets``); imports no ``PySide6``. The
boundary is injectable, so a built body is byte-stable and CI-testable.
"""
import base64
import re
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

Fields = Union[Mapping[str, str], Sequence[Tuple[str, str]], None]


@dataclass
class MultipartFile:
    """One file part of a multipart body."""

    name: str
    filename: str
    content: Union[str, bytes]
    content_type: str = "application/octet-stream"


def _to_bytes(value: Union[str, bytes]) -> bytes:
    return value if isinstance(value, bytes) else str(value).encode("utf-8")


def new_boundary() -> str:
    """Return a fresh multipart boundary token."""
    return "----AutoControlBoundary" + secrets.token_hex(16)


def _iter_fields(fields: Fields) -> List[Tuple[str, str]]:
    if fields is None:
        return []
    if isinstance(fields, Mapping):
        return list(fields.items())
    return list(fields)


# The HTML multipart/form-data encoding: a quote or line break in a name or
# filename would end the parameter or the header line, letting a caller-
# supplied name inject headers and whole extra parts.
_PARAM_ESCAPES = {'"': "%22", "\r": "%0D", "\n": "%0A"}
_PARAM_UNESCAPES = {value: key for key, value in _PARAM_ESCAPES.items()}


def _quote_param(value: str) -> str:
    return "".join(_PARAM_ESCAPES.get(char, char) for char in str(value))


def _unquote_param(value: str) -> str:
    return re.sub(r"%(22|0D|0A)", lambda match: _PARAM_UNESCAPES[match.group(0)], value)


def _field_part(boundary: str, name: str, value: str) -> bytes:
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{_quote_param(name)}"\r\n\r\n')
    return head.encode("utf-8") + _to_bytes(value) + b"\r\n"


def _as_file(spec: Union[MultipartFile, Mapping[str, Any]]) -> MultipartFile:
    if isinstance(spec, MultipartFile):
        return spec
    return MultipartFile(name=spec["name"], filename=spec["filename"],
                         content=spec["content"],
                         content_type=spec.get("content_type",
                                               "application/octet-stream"))


def _file_part(boundary: str, spec: MultipartFile) -> bytes:
    if "\r" in spec.content_type or "\n" in spec.content_type:
        raise ValueError(f"content_type contains a line break: {spec.content_type!r}")
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{_quote_param(spec.name)}"; '
            f'filename="{_quote_param(spec.filename)}"\r\n'
            f"Content-Type: {spec.content_type}\r\n\r\n")
    return head.encode("utf-8") + _to_bytes(spec.content) + b"\r\n"


def build_multipart(fields: Fields = None,
                    files: Optional[Sequence[Any]] = None, *,
                    boundary: Optional[str] = None) -> Tuple[str, bytes]:
    """Build a ``multipart/form-data`` body; return ``(content_type, body)``."""
    boundary = boundary or new_boundary()
    parts = [_field_part(boundary, name, value)
             for name, value in _iter_fields(fields)]
    parts.extend(_file_part(boundary, _as_file(spec)) for spec in (files or []))
    body = b"".join(parts) + f"--{boundary}--\r\n".encode("utf-8")
    return f"multipart/form-data; boundary={boundary}", body


def _boundary_of(content_type: str) -> Optional[str]:
    # Parameter names are case-insensitive: "Boundary=B" is the boundary too.
    match = re.search(r'(?i)boundary=("[^"]*"|[^;]+)', content_type or "")
    return match.group(1).strip().strip('"') if match else None


def _disp_params(header_block: bytes) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in header_block.decode("utf-8", "replace").split("\r\n"):
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    return headers


_DISPOSITION_PARAM = re.compile(r';\s*([^\s=;]+)\s*=\s*("(?:[^"\\]|\\.)*"|[^;]*)')


def _disposition_params(disposition: str) -> Dict[str, str]:
    """Parameters of a Content-Disposition value, quoted or bare.

    Splitting on every ";" broke a quoted ``filename="a;b.txt"``, and a bare
    token value (``name=a``) was dropped.
    """
    params: Dict[str, str] = {}
    for match in _DISPOSITION_PARAM.finditer(disposition):
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            # Only an escaped quote or backslash is unescaped: browsers send a
            # backslash as itself, so a\b.txt must stay a\b.txt.
            value = re.sub(r'\\(["\\])', r"\1", value[1:-1])
        params.setdefault(match.group(1).lower(), _unquote_param(value))
    return params


def _assign_part(headers: Mapping[str, str], content: bytes,
                 fields: Dict[str, str], files: List[Dict[str, Any]]) -> None:
    params = _disposition_params(headers.get("content-disposition", ""))
    name = params.get("name", "")
    if "filename" in params:
        # "content" is text for convenience; binary data (an image, a zip)
        # does not survive that decode, so the exact bytes ride along.
        files.append({"name": name, "filename": params["filename"],
                      "content_type": headers.get("content-type", ""),
                      "content": content.decode("utf-8", "replace"),
                      "content_base64": base64.b64encode(content).decode("ascii")})
    else:
        fields[name] = content.decode("utf-8", "replace")


def parse_multipart(content_type: str, body: bytes) -> Dict[str, Any]:
    """Parse a ``multipart/form-data`` body into ``{fields, files}``."""
    boundary = _boundary_of(content_type)
    if not boundary:
        raise ValueError("content_type has no multipart boundary")
    fields: Dict[str, str] = {}
    files: List[Dict[str, Any]] = []
    # A delimiter is CRLF + "--" + boundary; the CRLF belongs to it, not to
    # the part before. Stripping every CR and LF around a part cut the line
    # breaks a value ended with, and "--boundary" inside a line split it.
    chunks = (b"\r\n" + body).split(b"\r\n--" + boundary.encode("utf-8"))
    for chunk in chunks[1:]:
        if chunk.startswith(b"--"):
            break
        _, newline, part = chunk.partition(b"\r\n")  # transport padding
        if not newline:
            continue
        if part.startswith(b"\r\n"):
            head, content = b"", part[2:]
        else:
            head, sep, content = part.partition(b"\r\n\r\n")
            if not sep:
                continue
        _assign_part(_disp_params(head), content, fields, files)
    return {"fields": fields, "files": files}
