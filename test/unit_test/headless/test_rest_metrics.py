"""Tests for the Prometheus exposition layer (round 24)."""
from je_auto_control.utils.rest_api.rest_metrics import RestMetrics


def test_render_includes_required_families():
    metrics = RestMetrics()
    body = metrics.render()
    for family in (
        "autocontrol_rest_uptime_seconds",
        "autocontrol_rest_failed_auth_total",
        "autocontrol_rest_audit_rows",
        "autocontrol_active_sessions",
        "autocontrol_scheduler_jobs",
        "autocontrol_rest_requests_total",
    ):
        assert family in body, f"missing {family!r}"


def test_each_family_has_help_and_type():
    metrics = RestMetrics()
    body = metrics.render()
    families = [
        "autocontrol_rest_uptime_seconds",
        "autocontrol_rest_failed_auth_total",
        "autocontrol_rest_requests_total",
    ]
    for family in families:
        assert f"# HELP {family}" in body
        assert f"# TYPE {family}" in body


def test_record_request_increments_counter():
    metrics = RestMetrics()
    for _ in range(3):
        metrics.record_request("GET", "/health", 200)
    body = metrics.render()
    assert 'autocontrol_rest_requests_total{method="GET",path="/health",status="200"} 3' in body


def test_record_failed_auth_increments_counter():
    metrics = RestMetrics()
    metrics.record_failed_auth()
    metrics.record_failed_auth()
    body = metrics.render()
    assert "autocontrol_rest_failed_auth_total 2" in body


def test_label_escaping_handles_quotes_and_backslashes():
    metrics = RestMetrics()
    metrics.record_request("GET", '/weird"path\\with', 200)
    body = metrics.render()
    # Both quote and backslash must be escaped per Prometheus exposition spec.
    assert r'/weird\"path\\with' in body


def test_render_passes_through_extra_gauges():
    metrics = RestMetrics()
    body = metrics.render(audit_row_count=42, active_sessions=2,
                          scheduler_jobs=7)
    assert "autocontrol_rest_audit_rows 42" in body
    assert "autocontrol_active_sessions 2" in body
    assert "autocontrol_scheduler_jobs 7" in body
