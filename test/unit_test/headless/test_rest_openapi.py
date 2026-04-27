"""Tests for the OpenAPI spec generator + /openapi.json + /docs (round 35)."""
import json
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.rest_api.rest_openapi import (
    build_openapi_spec, known_endpoints,
)
from je_auto_control.utils.rest_api.rest_server import RestApiServer


_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server


@pytest.fixture()
def server():
    s = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    s.start()
    yield s
    s.stop(timeout=1.0)


def _get(server, path, *, token=None):
    host, port = server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{path}"
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        return (response.status, response.headers.get("Content-Type", ""),
                response.read())


def test_spec_has_required_top_level_fields():
    spec = build_openapi_spec()
    for key in ("openapi", "info", "servers", "paths", "components",
                "security", "tags"):
        assert key in spec, f"missing top-level key {key!r}"
    assert spec["openapi"].startswith("3.")


def test_spec_declares_bearer_security_scheme():
    spec = build_openapi_spec()
    schemes = spec["components"]["securitySchemes"]
    assert "BearerAuth" in schemes
    assert schemes["BearerAuth"]["type"] == "http"
    assert schemes["BearerAuth"]["scheme"] == "bearer"


def test_public_endpoints_override_security_to_empty():
    """/health, /dashboard, /docs are intentionally unauthenticated."""
    spec = build_openapi_spec()
    for path in ("/health", "/dashboard", "/docs"):
        op = spec["paths"][path]["get"]
        assert op.get("security") == [], (
            f"{path} should have security=[] (override of global)"
        )


def test_authenticated_endpoints_inherit_global_security():
    spec = build_openapi_spec()
    op = spec["paths"]["/sessions"]["get"]
    assert "security" not in op, (
        "authenticated endpoints should inherit global security, "
        "not declare their own"
    )


def test_post_endpoints_declare_request_body_schema():
    spec = build_openapi_spec()
    execute = spec["paths"]["/execute"]["post"]
    assert "requestBody" in execute
    body_schema = execute["requestBody"]["content"]["application/json"]["schema"]
    assert "actions" in body_schema["required"]


def test_query_parameters_are_documented():
    spec = build_openapi_spec()
    history = spec["paths"]["/history"]["get"]
    param_names = {p["name"] for p in history.get("parameters", [])}
    assert {"limit", "source_type"}.issubset(param_names)


def test_operation_ids_are_unique():
    spec = build_openapi_spec()
    ids = []
    for path_item in spec["paths"].values():
        for op in path_item.values():
            ids.append(op["operationId"])
    assert len(ids) == len(set(ids)), f"duplicate operationIds in {ids}"


def test_every_route_has_metadata():
    """Drift guard: any new entry in _GET_ROUTES / _POST_ROUTES (or the
    special /metrics, /dashboard, /openapi.json, /docs paths) MUST have
    matching metadata in rest_openapi._ENDPOINT_METADATA, or this test
    catches it.
    """
    from je_auto_control.utils.rest_api.rest_server import (
        _GET_ROUTES, _POST_ROUTES,
    )
    documented = set(known_endpoints())
    real: set = set()
    for path in _GET_ROUTES:
        real.add(("GET", path))
    for path in _POST_ROUTES:
        real.add(("POST", path))
    real.update({
        ("GET", "/metrics"),
        ("GET", "/dashboard"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
    })
    missing = real - documented
    extra = documented - real
    assert not missing, (
        f"OpenAPI metadata missing for routes: {sorted(missing)}. "
        f"Add an entry to _ENDPOINT_METADATA in rest_openapi.py."
    )
    assert not extra, (
        f"OpenAPI metadata documents non-existent routes: {sorted(extra)}"
    )


def test_openapi_endpoint_round_trips(server):
    status, ctype, body = _get(server, "/openapi.json", token=server.token)
    assert status == 200
    assert ctype.startswith("application/json")
    spec = json.loads(body.decode("utf-8"))
    assert "paths" in spec
    assert "/health" in spec["paths"]


def test_openapi_endpoint_requires_token(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(server, "/openapi.json")
    assert exc_info.value.code == 401


def test_docs_endpoint_serves_html_unauthenticated(server):
    status, ctype, body = _get(server, "/docs")
    assert status == 200
    assert ctype.startswith("text/html")
    text = body.decode("utf-8", errors="replace")
    assert "swagger-ui" in text
    assert "/openapi.json" in text


def test_docs_caches_token_in_session_storage(server):
    """The Swagger UI shell must use sessionStorage so the token does
    not survive a tab close (matches the dashboard's policy)."""
    _, _, body = _get(server, "/docs")
    text = body.decode("utf-8", errors="replace")
    assert "sessionStorage" in text
