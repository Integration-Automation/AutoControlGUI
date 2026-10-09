"""Move the files synced scripts refer to, verified by content hash.

A script that arrives without the template images it matches against fails
on its first step. Config sync lists such files in an :class:`AssetManifest`
-- relative path, SHA-256, size -- and :func:`sync_assets` brings each one in
through an :class:`AssetTransport`: the bytes are hashed before anything is
written, and the file is replaced atomically, so a transfer that was cut
short or tampered with never becomes a half-written or wrong file.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import hashlib
import json
import threading
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple

from je_auto_control.utils.config_sync.bucket import ConfigSyncError
from je_auto_control.utils.exception.exceptions import AutoControlException

_SHA256_HEX_CHARS = 64
#: Blobs stored more recently than this are left alone by
#: :func:`collect_unreferenced_blobs`: a machine uploads a file just before it
#: commits the entry that refers to it.
DEFAULT_BLOB_GRACE_S = 24 * 3600.0


class AssetSyncError(ConfigSyncError):
    """An asset could not be read, fetched, verified or written."""


def file_sha256(path: str | Path) -> str:
    """The SHA-256 of a file's content, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checked_digest(value: Any) -> str:
    text = str(value).lower()
    if len(text) != _SHA256_HEX_CHARS or any(char not in "0123456789abcdef" for char in text):
        raise AssetSyncError(f"not a SHA-256 hex digest: {value!r}")
    return text


@dataclass(frozen=True)
class AssetRef:
    """One file: where it belongs under the root, and what it must contain."""
    path: str
    sha256: str
    size: int

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class AssetManifest:
    """The files that should exist under ``root``, by relative posix path."""
    root: Path
    assets: Tuple[AssetRef, ...] = ()

    @classmethod
    def from_directory(cls, root: str | Path,
                       patterns: Iterable[str] = ("*",)) -> "AssetManifest":
        """List the files under ``root`` matching any of ``patterns`` (recursive)."""
        base = Path(root)
        found: Dict[str, AssetRef] = {}
        for pattern in patterns:
            for path in sorted(base.rglob(pattern)) if base.is_dir() else ():
                if path.is_file():
                    relative = path.relative_to(base).as_posix()
                    found[relative] = AssetRef(relative, file_sha256(path), path.stat().st_size)
        return cls(root=base, assets=tuple(found[key] for key in sorted(found)))

    @classmethod
    def from_entries(cls, root: str | Path,
                     entries: Mapping[str, Mapping[str, Any]]) -> "AssetManifest":
        """Build a manifest from ``{relative path: {"sha256": ..., "size": ...}}``."""
        refs = []
        for path, body in sorted(entries.items()):
            size = body.get("size", 0)
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise AssetSyncError(f"asset {path!r}: size must be an integer >= 0")
            refs.append(AssetRef(str(path), _checked_digest(body.get("sha256")), size))
        return cls(root=Path(root), assets=tuple(refs))

    def destination(self, asset: AssetRef) -> Path:
        """Where ``asset`` goes; refuses a path that would leave the root."""
        relative = PurePosixPath(asset.path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts \
                or ":" in asset.path or "\\" in asset.path:
            raise AssetSyncError(f"asset path {asset.path!r} does not stay inside the folder")
        target = self.root.joinpath(*relative.parts)
        root = self.root.resolve()
        if root != target.resolve() and root not in target.resolve().parents:
            raise AssetSyncError(f"asset path {asset.path!r} resolves outside the folder")
        return target


class AssetTransport(Protocol):
    """Where asset content travels: a content-addressed blob store.

    :class:`DirectoryAssetTransport` (a folder both machines reach) and
    :class:`HttpAssetTransport` (the sync server's ``/blobs`` routes) ship.
    """

    def fetch(self, sha256: str) -> bytes:
        """The content stored under ``sha256``; raise ``AssetSyncError`` if absent."""

    def store(self, sha256: str, data: bytes) -> None:
        """Keep ``data`` under ``sha256``."""

    def has(self, sha256: str) -> bool:
        """Whether content for ``sha256`` is already stored."""


class DirectoryAssetTransport:
    """An :class:`AssetTransport` over a folder both machines can reach.

    A shared drive, a mounted bucket or a folder another sync tool mirrors.
    Blobs are named by their hash, so identical files are stored once.
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def _blob(self, sha256: str) -> Path:
        return self._directory / _checked_digest(sha256)

    def fetch(self, sha256: str) -> bytes:
        """Read the blob stored under ``sha256``."""
        try:
            return self._blob(sha256).read_bytes()
        except OSError as error:
            raise AssetSyncError(f"asset {sha256} is not in {self._directory}: {error}") from error

    def store(self, sha256: str, data: bytes) -> None:
        """Write ``data`` under ``sha256`` atomically."""
        from je_auto_control.utils.json_store.json_store import atomic_write_bytes
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(self._blob(sha256), data)
        except OSError as error:
            raise AssetSyncError(f"cannot store asset {sha256}: {error}") from error

    def has(self, sha256: str) -> bool:
        """Whether the blob exists."""
        return self._blob(sha256).is_file()


_LISTING = "listing"
#: Why the server refused a blob request, by status.
_HTTP_REFUSALS = {
    400: "the server rejected the blob (bad digest or content)",
    401: "the shared secret was refused",
    404: "the server does not serve /blobs (it predates blob storage)",
    405: "the server does not serve /blobs (it predates blob storage)",
    411: "the server requires a Content-Length",
    413: "the file is larger than the server accepts for one blob",
    503: "the server's blob store is unavailable or holds too many accounts",
    507: "the account's blob quota on the server is used up",
}


class HttpAssetTransport:
    """An :class:`AssetTransport` over the sync server's ``/blobs`` routes.

    For machines that share a sync server and nothing else: no folder both
    can reach is needed. Blobs are kept per account under the same shared
    secret as the bucket (``PUT`` / ``GET`` / ``HEAD
    /blobs/{user_id}/{sha256}``), named by their hash, so identical files
    are stored once. The server limits the size of one blob and the total
    an account may hold; a file over either is reported per file by
    :func:`publish_assets` rather than stopping the others.

    The per-blob limit is read from the account's listing (``GET
    /blobs/{user_id}``) before the first upload and remembered, and a file
    over it is refused here without being sent. That matters for more than
    the saved upload: the server answers an oversized ``PUT`` from its
    declared length and closes the connection, and a client still sending
    the body can see the reset instead of the ``413`` -- the failure then
    read as a connection error. A server that does not say its limit is
    simply sent the file; if that upload is cut off the limit is asked for
    once more, so "too large" is still the reason given when it is the reason.

    Requests go through :mod:`je_auto_control.utils.http_client`, so the
    egress policy applies, and redirects are not followed -- the secret is
    never carried to another host.
    """

    def __init__(self, server_url: str, *, user_id: str, secret: Optional[str] = None,
                 timeout_s: float = 30.0) -> None:
        if not server_url:
            raise AssetSyncError("server_url is required")
        if not user_id:
            raise AssetSyncError("user_id is required")
        self._server_url = server_url.rstrip("/")
        self._user_id = user_id
        self._secret = secret
        self._timeout = float(timeout_s)
        self._max_blob_bytes: Optional[int] = None
        self._limit_asked = False

    def _listing_url(self) -> str:
        account = urllib.parse.quote(self._user_id, safe="")
        return f"{self._server_url}/blobs/{account}"

    def _url(self, sha256: str) -> str:
        return f"{self._listing_url()}/{_checked_digest(sha256)}"

    def _request(self, method: str, sha256: Optional[str],
                 data: Optional[bytes] = None) -> Dict[str, Any]:
        """One request about blob ``sha256``, or about the account's listing (``None``)."""
        from je_auto_control.utils.http_client.http_client import build_call, perform_call
        headers = {"Content-Type": "application/octet-stream"} if data is not None else {}
        if self._secret:
            headers["X-Signaling-Secret"] = self._secret
        try:
            url = self._listing_url() if sha256 is None else self._url(sha256)
            call = build_call(url, method=method, headers=headers, data=data,
                              timeout=self._timeout)
            call["follow_redirects"] = False
            call["want_bytes"] = method == "GET" and sha256 is not None
            return perform_call(call)
        except AssetSyncError:
            raise
        except (OSError, ValueError, AutoControlException) as error:
            raise AssetSyncError(
                f"asset {method} {sha256 or _LISTING} failed: {error}") from error

    @staticmethod
    def _json(response: Mapping[str, Any], what: str) -> Dict[str, Any]:
        try:
            body = json.loads(response.get("text") or "")
        except (json.JSONDecodeError, RecursionError) as error:
            raise AssetSyncError(f"asset {what}: the reply was not JSON") from error
        if not isinstance(body, dict):
            raise AssetSyncError(f"asset {what}: the reply was not a JSON object")
        return body

    def usage(self) -> Dict[str, Any]:
        """What the account holds on the server, and the server's limits.

        ``{"used", "quota", "count", "max_blob_bytes", "blobs": [{"sha256",
        "size", "age_s"}, ...]}`` as the server reports it; a server older
        than a field leaves it out. Raises :class:`AssetSyncError` when the
        server refuses or does not serve the listing.
        """
        response = self._request("GET", None)
        status = int(response["status"])
        if status != 200:
            raise self._refused("GET", _LISTING, status)
        listing = self._json(response, _LISTING)
        limit = listing.get("max_blob_bytes")
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
            self._max_blob_bytes = limit
        return listing

    def max_blob_bytes(self, *, refresh: bool = False) -> Optional[int]:
        """The largest blob the server accepts; ``None`` when it does not say.

        Asked once and remembered (``refresh`` asks again). A listing that
        cannot be had -- the server is unreachable, or predates it -- is not
        an error here: the limit is then unknown.
        """
        if refresh or not self._limit_asked:
            self._limit_asked = True
            try:
                self.usage()
            except AssetSyncError:
                pass
        return self._max_blob_bytes

    @staticmethod
    def _require_fits(sha256: str, size: int, limit: Optional[int],
                      cause: Optional[BaseException] = None) -> None:
        """Raise the "too large" refusal when ``size`` is over a known ``limit``."""
        if limit is not None and size > limit:
            raise AssetSyncError(
                f"asset PUT {sha256}: {_HTTP_REFUSALS[413]} "
                f"({size} bytes; the limit is {limit})") from cause

    @staticmethod
    def _refused(method: str, sha256: str, status: int) -> AssetSyncError:
        reason = _HTTP_REFUSALS.get(status, f"the server answered HTTP {status}")
        return AssetSyncError(f"asset {method} {sha256}: {reason}")

    def fetch(self, sha256: str) -> bytes:
        """Download the blob stored under ``sha256``."""
        response = self._request("GET", sha256)
        status = int(response["status"])
        if status == 404:
            raise AssetSyncError(f"asset {sha256} is not on the server")
        if status != 200:
            raise self._refused("GET", sha256, status)
        content = response.get("content")
        if not isinstance(content, (bytes, bytearray)):
            raise AssetSyncError(f"asset GET {sha256}: the reply carried no content")
        return bytes(content)

    def store(self, sha256: str, data: bytes) -> None:
        """Upload ``data`` under ``sha256``; the server checks the hash too.

        A file over the server's per-blob limit is refused without being
        sent, and always with the same reason (see the class docstring).
        """
        digest = _checked_digest(sha256)
        body = bytes(data)
        self._require_fits(digest, len(body), self.max_blob_bytes())
        try:
            status = int(self._request("PUT", digest, body)["status"])
        except AssetSyncError as error:
            # Cut off while sending: was it the size? Ask the limit afresh.
            self._require_fits(digest, len(body), self.max_blob_bytes(refresh=True), error)
            raise
        if status not in (200, 201):
            raise self._refused("PUT", digest, status)

    def has(self, sha256: str) -> bool:
        """Whether the server already holds the blob (so it need not be sent)."""
        status = int(self._request("HEAD", sha256)["status"])
        if status == 200:
            return True
        if status == 404:
            return False
        raise self._refused("HEAD", sha256, status)

    def delete(self, sha256: str) -> bool:
        """Remove the account's blob from the server; ``False`` when it held none."""
        response = self._request("DELETE", sha256)
        status = int(response["status"])
        if status == 404:
            return False
        if status != 200:
            raise self._refused("DELETE", sha256, status)
        return self._json(response, f"DELETE {sha256}").get("deleted") is True


@dataclass
class AssetSyncResult:
    """What :func:`sync_assets` or :func:`publish_assets` did.

    ``transferred`` and ``unchanged`` list relative paths, ``failed`` maps a
    path to why it was not written, ``hashes`` records the verified SHA-256
    of every file now in place.
    """
    transferred: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    failed: Dict[str, str] = field(default_factory=dict)
    hashes: Dict[str, str] = field(default_factory=dict)
    cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"transferred": list(self.transferred), "unchanged": list(self.unchanged),
                "failed": dict(self.failed), "hashes": dict(self.hashes),
                "cancelled": self.cancelled}


def _receive(manifest: AssetManifest, asset: AssetRef, transport: AssetTransport) -> bool:
    """Bring one asset in; whether a file was written."""
    from je_auto_control.utils.json_store.json_store import atomic_write_bytes
    target = manifest.destination(asset)
    wanted = _checked_digest(asset.sha256)
    try:
        if target.is_file() and file_sha256(target) == wanted:
            return False
        data = transport.fetch(wanted)
        if len(data) != asset.size or hashlib.sha256(data).hexdigest() != wanted:
            raise AssetSyncError("content does not match its SHA-256 and size; not written")
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, data)
    except OSError as error:
        raise AssetSyncError(str(error)) from error
    return True


def sync_assets(manifest: AssetManifest, transport: AssetTransport, *,
                cancel: Optional[threading.Event] = None) -> AssetSyncResult:
    """Make the files under ``manifest.root`` match the manifest.

    A file already holding the right content is left alone. Anything else is
    fetched, checked against its SHA-256 and size, and only then moved into
    place in one step -- the existing file stays untouched when the check
    fails. One bad asset does not stop the others; it is reported in
    ``failed``. Setting ``cancel`` stops before the next file.
    """
    result = AssetSyncResult()
    for asset in manifest.assets:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        try:
            written = _receive(manifest, asset, transport)
        except AssetSyncError as error:
            result.failed[asset.path] = str(error)
            continue
        (result.transferred if written else result.unchanged).append(asset.path)
        result.hashes[asset.path] = asset.sha256
    return result


def publish_assets(manifest: AssetManifest, transport: AssetTransport, *,
                   cancel: Optional[threading.Event] = None) -> AssetSyncResult:
    """Put the manifest's local files where other machines can fetch them.

    A file whose content no longer matches the manifest is reported in
    ``failed`` rather than stored under the wrong hash.
    """
    result = AssetSyncResult()
    for asset in manifest.assets:
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
        try:
            if transport.has(asset.sha256):
                result.unchanged.append(asset.path)
            else:
                data = manifest.destination(asset).read_bytes()
                if hashlib.sha256(data).hexdigest() != _checked_digest(asset.sha256):
                    raise AssetSyncError("file changed since the manifest was built")
                transport.store(asset.sha256, data)
                result.transferred.append(asset.path)
        except (AssetSyncError, OSError) as error:
            result.failed[asset.path] = str(error)
            continue
        result.hashes[asset.path] = asset.sha256
    return result


def _checked_grace(min_age_s: Any) -> float:
    if isinstance(min_age_s, bool) or not isinstance(min_age_s, (int, float)) \
            or not min_age_s >= 0:  # NOSONAR python:S1940  # reason: `< 0` would let NaN through
        raise AssetSyncError(f"min_age_s must be a number >= 0, got {min_age_s!r}")
    return float(min_age_s)


def _old_enough(age_s: Any, min_age_s: float) -> bool:
    """Whether a listed blob is past the grace period (an unknown age never is)."""
    if min_age_s <= 0:
        return True
    return isinstance(age_s, (int, float)) and not isinstance(age_s, bool) and age_s >= min_age_s


def _listed(blob: Any) -> Optional[Tuple[str, int, Any]]:
    """``(digest, size, age)`` of one listing row; ``None`` for a row that is not one."""
    if not isinstance(blob, Mapping):
        return None
    try:
        digest = _checked_digest(blob.get("sha256"))
    except AssetSyncError:
        return None
    size = blob.get("size")
    if isinstance(size, bool) or not isinstance(size, int):
        size = 0
    return digest, size, blob.get("age_s")


def collect_unreferenced_blobs(transport: HttpAssetTransport, referenced: Iterable[str], *,
                               min_age_s: float = DEFAULT_BLOB_GRACE_S,
                               dry_run: bool = False) -> Dict[str, Any]:
    """Delete the account's blobs on the server that ``referenced`` does not name.

    ``referenced`` is every SHA-256 still in use -- for config sync, the
    digests the bucket's entries name
    (:func:`~je_auto_control.utils.config_sync.session.referenced_blob_digests`;
    :func:`~je_auto_control.utils.config_sync.session.config_sync_collect_blobs`
    gathers them for you). A blob stored less than ``min_age_s`` ago is kept
    whatever it is: a machine uploads a file just before it commits the entry
    naming it, and that entry is not in anybody's bucket yet. The age is the
    server's own figure, so no two clocks are compared; a server that does
    not report ages has nothing collected unless ``min_age_s`` is ``0``.

    Returns ``{"deleted": [sha256...], "freed": bytes, "kept": count,
    "recent": [sha256...], "failed": {sha256: why}, "dry_run": bool}``. With
    ``dry_run`` nothing is deleted and ``deleted`` lists what would be.

    For :class:`HttpAssetTransport` only: its blobs belong to one account. A
    folder behind :class:`DirectoryAssetTransport` may hold other users'
    files, which nothing here could tell apart.
    """
    grace = _checked_grace(min_age_s)
    keep = {_checked_digest(digest) for digest in referenced}
    rows = transport.usage().get("blobs")
    result: Dict[str, Any] = {"deleted": [], "freed": 0, "kept": 0, "recent": [],
                              "failed": {}, "dry_run": bool(dry_run)}
    for digest, size, age in filter(None, map(_listed, rows if isinstance(rows, list) else ())):
        if digest in keep:
            result["kept"] += 1
        elif not _old_enough(age, grace):
            result["recent"].append(digest)
        elif _removed(transport, digest, dry_run, result["failed"]):
            result["deleted"].append(digest)
            result["freed"] += size
    return result


def _removed(transport: HttpAssetTransport, digest: str, dry_run: bool,
             failed: Dict[str, str]) -> bool:
    """Delete one blob (unless ``dry_run``); a failure is recorded, not raised."""
    if dry_run:
        return True
    try:
        transport.delete(digest)
    except AssetSyncError as error:
        failed[digest] = str(error)
        return False
    return True


__all__ = [
    "AssetManifest", "AssetRef", "AssetSyncError", "AssetSyncResult", "AssetTransport",
    "DEFAULT_BLOB_GRACE_S", "DirectoryAssetTransport", "HttpAssetTransport",
    "collect_unreferenced_blobs", "file_sha256", "publish_assets", "sync_assets",
]
