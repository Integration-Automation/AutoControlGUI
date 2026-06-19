"""S3-compatible artifact store for reports, screenshots, and recordings."""
from je_auto_control.utils.artifact_store.s3_store import (
    S3ArtifactStore, configure_default_store, get_default_store,
    set_default_store,
)

__all__ = [
    "S3ArtifactStore", "configure_default_store", "get_default_store",
    "set_default_store",
]
