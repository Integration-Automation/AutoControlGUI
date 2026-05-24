"""Ticket-backend abstractions and concrete Jira / Linear / GitHub
implementations. Network I/O uses ``urllib`` so the module has no
third-party dependencies; each backend exposes a single
``create_issue(report) -> TicketResult`` method that translates the
generic :class:`FailureReport` into the provider-specific payload.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from je_auto_control.utils.failure_hooks.report import (
    FailureReport, TicketResult,
)


_HTTP_TIMEOUT = 15.0


class TicketBackend(Protocol):
    """Pluggable ticket backend — implement ``create_issue`` and we'll call it."""

    name: str

    def create_issue(self, report: FailureReport) -> TicketResult: ...


@dataclass(frozen=True)
class JiraBackend:
    """Jira REST API v3: ``POST /rest/api/3/issue``."""

    base_url: str
    email: str
    api_token: str
    project_key: str
    issue_type: str = "Bug"
    name: str = "jira"

    def create_issue(self, report: FailureReport) -> TicketResult:
        url = f"{self.base_url.rstrip('/')}/rest/api/3/issue"
        body = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": report.render_summary(),
                "description": _adf_doc(report.render_body()),
                "issuetype": {"name": self.issue_type},
            },
        }
        token = base64.b64encode(
            f"{self.email}:{self.api_token}".encode("utf-8"),
        ).decode("ascii")
        return _post_json(self.name, url, body, headers={
            "Authorization": f"Basic {token}",
        }, id_key="key", url_template=f"{self.base_url}/browse/{{id}}")


@dataclass(frozen=True)
class LinearBackend:
    """Linear GraphQL endpoint: ``POST /graphql`` with ``issueCreate``."""

    api_key: str
    team_id: str
    base_url: str = "https://api.linear.app"
    name: str = "linear"

    def create_issue(self, report: FailureReport) -> TicketResult:
        url = f"{self.base_url.rstrip('/')}/graphql"
        query = (
            "mutation($teamId: String!, $title: String!, $description: String!) {"
            "  issueCreate(input: {teamId: $teamId, title: $title, "
            "description: $description}) {"
            "    success issue { identifier url }"
            "  }"
            "}"
        )
        body = {
            "query": query,
            "variables": {
                "teamId": self.team_id,
                "title": report.render_summary(),
                "description": report.render_body(),
            },
        }
        return _post_json(self.name, url, body, headers={
            "Authorization": self.api_key,
        }, response_extractor=_extract_linear_response)


@dataclass(frozen=True)
class GitHubBackend:
    """GitHub Issues REST API: ``POST /repos/{owner}/{repo}/issues``."""

    owner: str
    repo: str
    token: str
    base_url: str = "https://api.github.com"
    name: str = "github"

    def create_issue(self, report: FailureReport) -> TicketResult:
        url = (f"{self.base_url.rstrip('/')}/repos/"
               f"{self.owner}/{self.repo}/issues")
        body = {
            "title": report.render_summary(),
            "body": report.render_body(),
            "labels": ["autocontrol-failure"],
        }
        return _post_json(self.name, url, body, headers={
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
        }, id_key="number", url_key="html_url")


def _post_json(backend_name: str, url: str, body: Dict[str, Any], *,
                headers: Dict[str, str],
                id_key: Optional[str] = None,
                url_key: Optional[str] = None,
                url_template: Optional[str] = None,
                response_extractor=None) -> TicketResult:
    """Shared HTTP POST helper used by every backend."""
    # NOSONAR python:S5332 — scheme allow-list check, not URL emission;
    # http:// is permitted for self-hosted Jira on a trusted LAN.
    if not url.startswith(("https://", "http://")):
        return TicketResult(
            backend=backend_name, succeeded=False,
            error=f"refusing to call non-HTTP(S) URL: {url}",
        )
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # nosec B310  # reason: scheme guard above
        url, data=data, method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(  # nosec B310
                request, timeout=_HTTP_TIMEOUT,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        return TicketResult(
            backend=backend_name, succeeded=False, error=str(error),
        )
    except ValueError as error:
        return TicketResult(
            backend=backend_name, succeeded=False,
            error=f"non-JSON response: {error}",
        )
    if response_extractor is not None:
        return response_extractor(backend_name, payload)
    return _generic_extract(
        backend_name, payload, id_key=id_key, url_key=url_key,
        url_template=url_template,
    )


def _generic_extract(backend_name: str, payload: Dict[str, Any], *,
                      id_key: Optional[str],
                      url_key: Optional[str],
                      url_template: Optional[str]) -> TicketResult:
    ticket_id = str(payload.get(id_key)) if id_key and payload.get(id_key) else None
    direct_url = (
        str(payload.get(url_key)) if url_key and payload.get(url_key) else None
    )
    url = direct_url or (
        url_template.format(id=ticket_id) if (url_template and ticket_id) else None
    )
    return TicketResult(
        backend=backend_name, succeeded=ticket_id is not None,
        ticket_id=ticket_id, url=url,
        error=None if ticket_id else f"missing {id_key!r} in response",
    )


def _extract_linear_response(backend_name: str,
                              payload: Dict[str, Any]) -> TicketResult:
    data = ((payload.get("data") or {}).get("issueCreate")) or {}
    if not data.get("success"):
        errors = payload.get("errors") or data.get("error") or "unknown"
        return TicketResult(
            backend=backend_name, succeeded=False, error=str(errors),
        )
    issue = data.get("issue") or {}
    return TicketResult(
        backend=backend_name, succeeded=True,
        ticket_id=str(issue.get("identifier", "")),
        url=str(issue.get("url", "")) or None,
    )


def _adf_doc(text: str) -> Dict[str, Any]:
    """Wrap a plain-text body in Jira's Atlassian Document Format envelope."""
    return {
        "type": "doc", "version": 1,
        "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }],
    }


__all__ = ["GitHubBackend", "JiraBackend", "LinearBackend", "TicketBackend"]
