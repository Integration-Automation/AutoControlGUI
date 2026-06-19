"""Push automation artifacts to S3-compatible object storage.

Reports, screenshots, and screen recordings produced by a run are usually worth
keeping off the runner. ``S3ArtifactStore`` uploads/downloads/lists/deletes them
against any S3-compatible bucket (AWS S3, MinIO, R2, …). ``boto3`` is an
**optional** dependency (``pip install je_auto_control[s3]``): the S3 client is
injectable, so the store's logic is fully unit-testable with a fake client and
``boto3`` is imported only when no client is supplied.

A module-level default store (configured once via :func:`configure_default_store`
or :func:`set_default_store`) backs the executor/MCP commands. Object keys are
prefixed and normalised to forward slashes. Imports no ``PySide6``.
"""
from pathlib import Path
from typing import Any, List, Optional


def _build_boto3_client() -> Any:  # pragma: no cover - requires boto3 + creds
    import boto3
    return boto3.client("s3")


class S3ArtifactStore:
    """Upload/download/list/delete artifacts in one S3-compatible bucket."""

    def __init__(self, bucket: str, *, client: Optional[Any] = None,
                 prefix: str = "") -> None:
        """``client`` is an S3 client (boto3 or a fake); built lazily if None."""
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = client

    @property
    def client(self) -> Any:
        """The S3 client, lazily built via boto3 on first use."""
        if self._client is None:
            self._client = _build_boto3_client()
        return self._client

    def _key(self, name: str) -> str:
        """Map a store-relative name to its full (prefixed) object key."""
        name = name.replace("\\", "/").lstrip("/")
        return f"{self._prefix}/{name}" if self._prefix else name

    def _relative(self, full_key: str) -> str:
        """Strip the store prefix from a full object key."""
        if self._prefix and full_key.startswith(self._prefix + "/"):
            return full_key[len(self._prefix) + 1:]
        return full_key

    def upload(self, local_path: str, key: Optional[str] = None) -> str:
        """Upload ``local_path``; return the store-relative key."""
        relative = key or Path(local_path).name
        self.client.upload_file(local_path, self._bucket, self._key(relative))
        return relative

    def download(self, key: str, local_path: str) -> str:
        """Download store-relative object ``key`` to ``local_path``."""
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self._bucket, self._key(key), str(target))
        return str(target)

    def list(self, prefix: Optional[str] = None) -> List[str]:
        """List store-relative object keys, optionally under extra ``prefix``."""
        response = self.client.list_objects_v2(
            Bucket=self._bucket, Prefix=self._key(prefix) if prefix
            else self._prefix)
        return [self._relative(item["Key"])
                for item in response.get("Contents", [])]

    def delete(self, key: str) -> bool:
        """Delete store-relative object ``key``; return ``True``."""
        self.client.delete_object(Bucket=self._bucket, Key=self._key(key))
        return True

    def url(self, key: str) -> str:
        """Return the ``s3://`` URL for store-relative object ``key``."""
        return f"s3://{self._bucket}/{self._key(key)}"


_STATE: dict = {"store": None}


def set_default_store(store: Optional[S3ArtifactStore]) -> None:
    """Install (or clear) the module-level default artifact store."""
    _STATE["store"] = store


def configure_default_store(bucket: str, *, client: Optional[Any] = None,
                            prefix: str = "") -> S3ArtifactStore:
    """Build and install the default store; return it."""
    store = S3ArtifactStore(bucket, client=client, prefix=prefix)
    set_default_store(store)
    return store


def get_default_store() -> S3ArtifactStore:
    """Return the default store or raise if it has not been configured."""
    store = _STATE["store"]
    if store is None:
        raise RuntimeError(
            "no default artifact store; call configure_default_store(bucket)")
    return store
