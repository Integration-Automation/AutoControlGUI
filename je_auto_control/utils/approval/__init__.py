"""Approval testing: verify artifacts against an approved baseline."""
from je_auto_control.utils.approval.approval_test import (
    ApprovalResult, approve_artifact, pending_artifacts, verify_artifact,
)

__all__ = [
    "ApprovalResult", "approve_artifact", "pending_artifacts",
    "verify_artifact",
]
