"""Canonical bounded base64 chunks keep binary asset traffic inside the existing authenticated JSON body limit."""
import base64
import binascii

from je_auto_control.utils.config_sync.blob_models import CHUNK_BYTES
from je_auto_control.utils.config_sync.contract import ConfigSyncError


def encode_chunk(body: bytes) -> str:
    """Encode one nonempty bounded immutable chunk without loading a complete asset."""
    if not isinstance(body, bytes) or not 1 <= len(body) <= CHUNK_BYTES:
        raise ConfigSyncError('asset chunk exceeds its binary size limit')
    return base64.b64encode(body).decode('ascii')


def decode_chunk(value: object) -> bytes:
    """Refuse oversized, noncanonical or invalid base64 before it reaches chunk storage."""
    if not isinstance(value, str) or not 0 < len(value) <= ((CHUNK_BYTES + 2) // 3) * 4:
        raise ConfigSyncError('asset chunk exceeds its encoded size limit')
    try:
        body = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ConfigSyncError('invalid asset chunk encoding') from error
    if encode_chunk(body) != value:
        raise ConfigSyncError('noncanonical asset chunk encoding')
    return body
