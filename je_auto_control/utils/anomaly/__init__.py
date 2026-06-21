"""Single-series anomaly detection for AutoControl."""
from je_auto_control.utils.anomaly.anomaly import (
    detect_anomalies, ewma_control, mad_anomalies, mad_scores,
    zscore_anomalies, zscore_scores,
)

__all__ = [
    "detect_anomalies", "ewma_control", "mad_anomalies", "mad_scores",
    "zscore_anomalies", "zscore_scores",
]
