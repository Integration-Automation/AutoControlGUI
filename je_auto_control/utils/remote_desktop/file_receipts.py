"""Immutable local publication receipts keep received bytes distinct from later edits to their target path."""
from dataclasses import dataclass
from pathlib import Path

from je_auto_control.utils.exception.exceptions import AutoControlException


class FileReceiptError(AutoControlException, ValueError):
    """A local file-publication receipt contains invalid metadata."""


@dataclass(frozen=True)
class FileReceiveReceipt:
    """Describe bytes atomically published by a local receiver; this is not a remote acknowledgement."""

    path: Path
    sha256: str
    size: int

    def __post_init__(self) -> None:
        """Validate immutable metadata without reading target content; bind relative paths to the publication cwd."""
        if not isinstance(self.path, Path):
            raise FileReceiptError('receipt path must be a Path')
        if (not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(char not in '0123456789abcdef' for char in self.sha256)):
            raise FileReceiptError('receipt digest must be a lowercase SHA-256 value')
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise FileReceiptError('receipt size must be a nonnegative integer')
        object.__setattr__(self, 'path', self.path.absolute())
