"""Build and parse ``multipart/form-data`` bodies (file upload support).

``http_request`` sends only JSON or raw bodies — there was no file upload, and
the stdlib ``cgi`` module (which once parsed multipart) was removed in Python
3.13. This assembles a ``multipart/form-data`` body from text fields and files
with a deterministic boundary, and parses one back.

Pure standard library (``re`` / ``secrets``); imports no ``PySide6``. The
boundary is injectable, so a built body is byte-stable and CI-testable.
"""
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


def _field_part(boundary: str, name: str, value: str) -> bytes:
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
    return head.encode("utf-8") + _to_bytes(value) + b"\r\n"


def _as_file(spec: Union[MultipartFile, Mapping[str, Any]]) -> MultipartFile:
    if isinstance(spec, MultipartFile):
        return spec
    return MultipartFile(name=spec["name"], filename=spec["filename"],
                         content=spec["content"],
                         content_type=spec.get("content_type",
                                               "application/octet-stream"))


def _file_part(boundary: str, spec: MultipartFile) -> bytes:
    head = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{spec.name}"; '
            f'filename="{spec.filename}"\r\n'
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
    match = re.search(r"boundary=([^;]+)", content_type or "")
    return match.group(1).strip().strip('"') if match else None


def _disp_params(header_block: bytes) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in header_block.decode("utf-8", "replace").split("\r\n"):
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()
    return headers


def _disposition_params(disposition: str) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for segment in disposition.split(";"):
        key, sep, value = segment.partition("=")
        value = value.strip()
        if sep and len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            params[key.strip()] = value[1:-1]
    return params


def _assign_part(headers: Mapping[str, str], content: bytes,
                 fields: Dict[str, str], files: List[Dict[str, Any]]) -> None:
    params = _disposition_params(headers.get("content-disposition", ""))
    name = params.get("name", "")
    if "filename" in params:
        files.append({"name": name, "filename": params["filename"],
                      "content_type": headers.get("content-type", ""),
                      "content": content.decode("utf-8", "replace")})
    else:
        fields[name] = content.decode("utf-8", "replace")


def parse_multipart(content_type: str, body: bytes) -> Dict[str, Any]:
    """Parse a ``multipart/form-data`` body into ``{fields, files}``."""
    boundary = _boundary_of(content_type)
    if not boundary:
        raise ValueError("content_type has no multipart boundary")
    fields: Dict[str, str] = {}
    files: List[Dict[str, Any]] = []
    for chunk in body.split(b"--" + boundary.encode("utf-8")):
        trimmed = chunk.strip(b"\r\n")
        if not trimmed or trimmed == b"--":
            continue
        head, sep, content = trimmed.partition(b"\r\n\r\n")
        if sep:
            _assign_part(_disp_params(head), content, fields, files)
    return {"fields": fields, "files": files}
