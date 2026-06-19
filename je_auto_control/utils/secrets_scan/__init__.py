"""Scan action JSON / data for hardcoded secrets that should be vaulted."""
from je_auto_control.utils.secrets_scan.secrets_scan import scan_secrets

__all__ = ["scan_secrets"]
