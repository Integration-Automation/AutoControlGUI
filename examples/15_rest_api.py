"""Start the REST API server and call it from the same process.

The REST API exposes ``AC_*`` commands over HTTP, so any language with
an HTTP client can drive AutoControl. Pass ``token=`` to require a
Bearer header on every non-public endpoint.

Endpoints used here:

* ``GET /screen_size`` — read-only, returns ``{"width", "height"}``.
* ``POST /execute``    — runs a JSON ``{"actions": [...]}`` payload.

See ``je_auto_control.utils.rest_api.rest_server`` for the full route
table.
"""
import json
import secrets
import urllib.request

import je_auto_control as ac


def main() -> None:
    token = secrets.token_urlsafe(24)
    server = ac.start_rest_api_server(
        host="127.0.0.1", port=0, token=token,
    )
    host, port = server.address
    print(f"REST API listening on http://{host}:{port}  (token={token[:8]}…)")

    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}

    # GET /screen_size — simple read-only call.
    with urllib.request.urlopen(
            urllib.request.Request(
                f"http://{host}:{port}/screen_size", headers=headers,
            ),
            timeout=5.0,
    ) as resp:
        print(f"GET /screen_size  → {resp.read().decode('utf-8')}")

    # POST /execute — run an arbitrary action list.
    payload = json.dumps({
        "actions": [
            ["AC_screenshot", {"file_path": "rest_demo.png"}],
        ],
    }).encode("utf-8")
    with urllib.request.urlopen(
            urllib.request.Request(
                f"http://{host}:{port}/execute",
                data=payload, headers=headers, method="POST",
            ),
            timeout=10.0,
    ) as resp:
        print(f"POST /execute    → {resp.read().decode('utf-8')}")

    server.stop()


if __name__ == "__main__":
    main()
