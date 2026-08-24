"""Every REST route, called the way its own OpenAPI document says to call it.

`rest_handlers` is the third registry of the same shape as the MCP tool table
and the `AC_*` dispatch table: thirty-odd functions that take a decoded request,
call one headless function, and return `(status, payload)` for the dispatcher to
write out as JSON. Its module docstring says the handlers are "pure ... trivial
to unit-test without an HTTP layer", and the existing REST tests go through the
HTTP layer instead, so on a headless runner most of them reach a handler only to
watch it fall into its own `except` and answer 500. The happy path -- the branch
a real client actually gets -- was checked by nobody.

The arguments come from `rest_openapi.build_openapi_spec()`, which is built from
`_ENDPOINT_METADATA` in a different module from the handlers. That matters for
the same reason the MCP sweep reads `_factories.py`: a sweep that took its
arguments from the handler it is testing could not fail. Here it also buys a
contract test for free -- a route the document does not describe, or a documented
route nothing serves, is a defect either way, and `test_the_route_table_and_the_
document_agree` says so by name.

Two things are asserted about every route:

* **It answers.** No route may raise: the dispatcher writes the handler's return
  value straight into the socket, so an exception is a dropped HTTP response and
  a client that hangs until it times out. This holds for a well-formed request
  and for the empty one an unhelpful client sends.
* **The answer is JSON with an HTTP status.** `(int, dict)`, a status in the
  100-599 range, and a payload `json.dumps` accepts.

The callee is replaced by a stub grown from its own return annotation, exactly
as in the other two sweeps -- see `_contract_sweep`.
"""
import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import pytest

from headless._contract_sweep import (
    contract_stubs, install_stubs, is_serialisable, sample_value,
)
from je_auto_control.utils.rest_api import rest_server
from je_auto_control.utils.rest_api.rest_handlers import RouteContext
from je_auto_control.utils.rest_api.rest_openapi import build_openapi_spec

_SPEC = build_openapi_spec()
_JSON = "application/json"

# Served by the dispatcher itself rather than from the two route tables,
# because none of them answers with JSON: Prometheus text, the dashboard HTML
# and the Swagger UI page. They are in the document because a client still has
# to be told they exist.
_NOT_JSON_ROUTES = {("GET", "/dashboard"), ("GET", "/docs"), ("GET", "/metrics")}


@pytest.fixture(autouse=True)
def _in_a_directory_of_its_own(tmp_path, monkeypatch):
    """Run every sweep case in an empty directory.

    An adapter whose callee is a class builds the real object out of the
    client's own arguments, and some of those objects are stores: a
    checkpoint store handed the sample file path creates a SQLite database
    where it stands. In the repository that leaves files behind and makes one
    case depend on whether another ran first; here each case gets a directory
    nobody else can see.
    """
    monkeypatch.chdir(tmp_path)


def _routes() -> List[Tuple[str, str, Any]]:
    """Every `(method, path, handler)` the dispatcher can reach."""
    return ([("GET", path, handler)
             for path, handler in rest_server._GET_ROUTES.items()]
            + [("POST", path, handler)
               for path, handler in rest_server._POST_ROUTES.items()])


ROUTES = sorted(_routes(), key=lambda route: (route[0], route[1]))
_IDS = [f"{method} {path}" for method, path, _ in ROUTES]


def _operation(method: str, path: str) -> Dict[str, Any]:
    return _SPEC["paths"].get(path, {}).get(method.lower(), {})


def _query_for(operation: Dict[str, Any]) -> str:
    """Build a query string from the operation's declared parameters."""
    pairs = [(parameter["name"],
              sample_value(parameter.get("schema") or {}, parameter["name"]))
             for parameter in operation.get("parameters", [])
             if parameter.get("in") == "query"]
    return urlencode([(name, str(value)) for name, value in pairs])


def _body_for(operation: Dict[str, Any]) -> Optional[Any]:
    """Build a request body from the operation's declared requestBody."""
    content = (operation.get("requestBody") or {}).get("content") or {}
    schema = (content.get(_JSON) or {}).get("schema")
    if not schema:
        return None
    return {name: sample_value(spec, name)
            for name, spec in (schema.get("properties") or {}).items()}


def _assert_answers_json(result: Any, label: str) -> None:
    """A handler's return value is what the dispatcher writes to the socket."""
    assert isinstance(result, tuple) and len(result) == 2, (
        f"{label} returned {result!r}, not (status, payload)")
    status, payload = result
    assert isinstance(status, int) and 100 <= status <= 599, (
        f"{label} returned {status!r}, which is not an HTTP status")
    assert isinstance(payload, dict), (
        f"{label} returned a {type(payload).__name__} payload; the dispatcher "
        "writes a JSON object")
    assert is_serialisable(payload), (
        f"{label} returned a payload json.dumps cannot encode")


# === The document and the table have to describe the same API ===============

def test_the_route_table_and_the_document_agree():
    """A route nobody documents, or a documented route nobody serves."""
    documented = {(method.upper(), path)
                  for path, item in _SPEC["paths"].items() for method in item}
    routed = {(method, path) for method, path, _ in ROUTES}
    assert routed - documented == set(), (
        "routes the OpenAPI document does not describe: "
        f"{sorted(routed - documented)}")
    assert documented - routed == _NOT_JSON_ROUTES, (
        "documented routes nothing serves, or a non-JSON route that grew a "
        f"JSON handler: {sorted(documented - routed - _NOT_JSON_ROUTES)}")


def test_every_route_is_reachable_from_the_dispatcher():
    """The two tables are what `handle_request` looks in; neither may be empty."""
    assert len(rest_server._GET_ROUTES) > 10
    assert len(rest_server._POST_ROUTES) > 5
    assert not set(rest_server._GET_ROUTES) & set(rest_server._POST_ROUTES), (
        "a path in both tables would resolve by method alone; nothing here "
        "expects that today")


# === Every route answers, twice ==============================================

@pytest.mark.parametrize("method, path, handler", ROUTES, ids=_IDS)
def test_a_documented_request_gets_a_json_answer(method, path, handler,
                                                 monkeypatch):
    """Called as the document says, every route answers in JSON."""
    operation = _operation(method, path)
    stubs = contract_stubs(handler)
    if stubs is not None:
        install_stubs(monkeypatch, stubs)
    context = RouteContext(query=_query_for(operation),
                           body=_body_for(operation),
                           client_ip="127.0.0.1")
    _assert_answers_json(handler(context), f"{method} {path}")


@pytest.mark.parametrize("method, path, handler", ROUTES, ids=_IDS)
def test_an_empty_request_gets_a_json_answer(method, path, handler,
                                             monkeypatch):
    """A client that sends nothing gets a status, not a dropped connection."""
    stubs = contract_stubs(handler)
    if stubs is not None:
        install_stubs(monkeypatch, stubs)
    context = RouteContext(query="", body=None, client_ip="127.0.0.1")
    _assert_answers_json(handler(context), f"{method} {path}")


@pytest.mark.parametrize("method, path, handler", ROUTES, ids=_IDS)
def test_a_body_of_the_wrong_shape_is_rejected_not_raised(method, path,
                                                          handler,
                                                          monkeypatch):
    """Bodies arrive from the network; a list where a dict was expected is
    the client's mistake to be told about, not the server's to crash on."""
    stubs = contract_stubs(handler)
    if stubs is not None:
        install_stubs(monkeypatch, stubs)
    context = RouteContext(query="limit=not-a-number&n=not-a-number",
                           body=["not", "an", "object"],
                           client_ip="127.0.0.1")
    _assert_answers_json(handler(context), f"{method} {path}")


# === The sweep has to keep finding things ====================================

def test_the_sweep_covers_the_whole_table():
    """A broken matcher would sweep nothing and still look green."""
    assert len(ROUTES) >= 30, f"only {len(ROUTES)} routes discovered"
    stubbable = [route for route in ROUTES if contract_stubs(route[2])]
    assert len(stubbable) > len(ROUTES) // 3, (
        f"only {len(stubbable)} of {len(ROUTES)} handlers could be stubbed "
        "from their callee's annotations -- the typing contract or the "
        "matcher has drifted")


# === The pieces the routes are built from ====================================

def test_query_parsing_takes_the_first_value_and_falls_back():
    context = RouteContext(query="limit=5&limit=9&other=x", body=None,
                           client_ip="127.0.0.1")
    assert context.query_first("limit") == "5"
    assert context.query_first("missing") is None
    assert context.query_first("missing", "fallback") == "fallback"
    assert context.query_params()["limit"] == ["5", "9"]


def test_a_route_without_a_query_string_parses_to_nothing():
    context = RouteContext(query="", body=None, client_ip="127.0.0.1")
    assert context.query_params() == {}
    assert context.query_first("limit", "100") == "100"


def test_health_is_the_one_route_that_needs_no_token():
    """A liveness probe must not need the bearer token the server minted."""
    assert rest_server._PUBLIC_PATHS == frozenset({"/health"})
    status, payload = rest_server.handle_health(
        RouteContext(query="", body=None, client_ip="127.0.0.1"))
    assert (status, payload) == (200, {"status": "ok"})


def test_the_published_document_is_json_and_describes_this_api():
    spec = json.loads(json.dumps(_SPEC))
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"]
    assert spec["paths"]
