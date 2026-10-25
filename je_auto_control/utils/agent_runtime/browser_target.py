"""Own a WebRunner SDK session inside a managed helper, without importing browser engines."""
# pylint: disable=import-outside-toplevel  # reason: optional SDK and executor imports must remain lazy
from __future__ import annotations

from typing import Any, Callable, Mapping
import uuid
from concurrent.futures import CancelledError

from je_auto_control.utils.agent_runtime.browser_commands import (
    BROWSER_ADAPTER_TOOLS, BROWSER_TRANSFER_TOOLS, browser_session_scope,
)
from je_auto_control.utils.agent_runtime.errors import AgentTaskError, AgentHumanReview
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.agent_runtime.target_continuity import require_context_continuity
from je_auto_control.utils.agent_runtime.browser_retirement import retirement_proof
from je_auto_control.utils.agent_runtime.browser_readonly_scope import readonly_verification_scope


def _open_session(origins: tuple[str, ...], *, transfer: bool = False) -> Any:
    try:
        from je_web_runner.api.ai import BrowserOriginPolicy, ManagedBrowserSession
    except ImportError:
        raise AgentTaskError(
            "install reviewed je_web_runner with managed-session support in the helper environment") from None
    version = getattr(ManagedBrowserSession, "contract_version", None)
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise AgentTaskError("je_web_runner managed browser contract version 1 is required before startup")
    if transfer:
        _require_transfers(ManagedBrowserSession)
    return ManagedBrowserSession.open(BrowserOriginPolicy(origins))


def _require_transfers(session_class: Any) -> None:
    marker = getattr(session_class, "transfer_contract_version", None)
    methods = ("link", "open_download", "upload")
    if not isinstance(marker, int) or isinstance(marker, bool) or marker != 1 or not all(
            callable(getattr(session_class, key, None)) for key in methods):
        raise AgentTaskError("je_web_runner managed transfer contract version 1 is required before startup")


def _task_origins(spec: AgentTaskSpec) -> tuple[str, ...]:
    origins = spec.options.get("allowed_origins", ())
    if spec.apps or not origins or not set(spec.allowed_tools) <= BROWSER_ADAPTER_TOOLS:
        raise AgentTaskError("browser tasks require explicit origins and reviewed browser-only tools")
    if not isinstance(origins, (list, tuple)) or len(origins) > 50:
        raise AgentTaskError("browser task origins must be bounded")
    return tuple(origins)


class BrowserTarget:
    """A fresh headless browser with task origins intersected by its immutable host profile."""

    def __init__(self) -> None:
        self._session: Any = None
        self._identity = uuid.uuid4().hex
        self._spec: AgentTaskSpec | None = None
        self._readonly: str | None = None
        self._reader_spec: AgentTaskSpec | None = None

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Open only after the host has pinned and checked its browser profile and task tools."""
        if self._readonly is not None:
            raise AgentTaskError("read-only browser cannot be reconfigured")
        if self._session is not None:
            if self._spec != spec:
                raise AgentTaskError("managed browser session cannot be rebound to another task scope")
            return True, ""
        origins = _task_origins(spec)
        try:
            self._session = (_open_session(tuple(origins), transfer=True)
                             if set(spec.allowed_tools) & BROWSER_TRANSFER_TOOLS else _open_session(tuple(origins)))
            self._session.set_timeout(spec.budget.action_seconds)
            self._spec = spec
            self._identity = uuid.uuid4().hex
        except AgentTaskError:
            self.cleanup()
            raise
        except Exception:  # noqa: BLE001 - contain optional SDK errors without publishing raw browser data
            self.cleanup()
            raise AgentTaskError("managed WebRunner startup failed; check installed SDK/browser readiness") from None
        return True, ""

    @property
    def can_freeze_readonly(self) -> bool:
        """Inspect actual SDK API availability only, without claiming retirement or native readiness."""
        marker = getattr(self._session, "readonly_contract_version", None)
        # pylint: disable-next=unidiomatic-typecheck  # reason: SDK contract versions exclude booleans
        return (self._session is not None and type(marker) is int and marker == 1
                and callable(getattr(self._session, "freeze_readonly", None)))

    @property
    def input_retired(self) -> bool:
        """Report the monotonic input gate, independently of whether SDK cleanup was confirmed."""
        return self._readonly is not None

    def freeze_readonly(self) -> dict:
        """Permanently retire the actual SDK owner before issuing any same-context proof."""
        if self._readonly is not None:
            return self.readonly_capabilities()
        if not self.can_freeze_readonly:
            return {"supported": False}
        self._readonly = ""
        try:
            identity = self._session.context_id
            if not isinstance(identity, str):
                raise AgentTaskError("browser retirement context is unconfirmed")
            self._session = self._session.freeze_readonly()
            result = retirement_proof(self._session.capabilities(), identity)
        except Exception:  # noqa: BLE001  # reason: contain optional SDK failures without input revival or data leaks
            raise AgentTaskError("browser retirement is unconfirmed") from None
        self._readonly = result["context_id"]
        return result

    def readonly_capabilities(self) -> dict:
        """Check the current actual SDK view rather than trusting a saved description."""
        if not self._readonly or self._session is None:
            raise AgentTaskError("browser retirement is unconfirmed")
        try:
            return retirement_proof(self._session.capabilities(), self._readonly)
        except Exception:  # noqa: BLE001  # reason: SDK faults stay bounded and leave this target permanently read-only
            self._readonly = ""
            raise AgentTaskError("browser retirement is unconfirmed") from None

    @property
    def readonly_spec(self) -> AgentTaskSpec:
        """Separate current verification scope from the immutable original input specification."""
        if self._spec is None:
            raise AgentTaskError("read-only browser has no original scope")
        return self._reader_spec if self._reader_spec is not None else self._spec

    def bind_readonly(self, value: Any, *, validate: Callable[[AgentTaskSpec], Any]) -> dict:
        """Bind only a host-admitted no-action verification scope; never configure or launch input."""
        proof = self.readonly_capabilities()
        if self._spec is None:
            raise AgentTaskError("read-only browser has no original scope")
        proposed = AgentTaskSpec.from_dict(value)
        readonly_verification_scope(self._spec, proposed)
        validate(proposed)
        self._reader_spec = proposed
        return proof

    def check_resume(self, spec: AgentTaskSpec, receipts: list[dict]) -> None:
        """Refuse a finite prefix after context retirement; an unchanged live context remains usable."""
        require_context_continuity(spec, receipts, self._session is not None and self._spec == spec, kind="browser")

    def observe(self) -> dict:
        """Flatten semantic main/frame elements into observation-local indexes; no values or image files."""
        if self._session is None:
            raise AgentTaskError("browser session is unavailable")
        try:
            raw = detached(self._session.observe())
        except Exception as error:  # noqa: BLE001 - SDK errors must stay inside the AutoControl error family
            if getattr(error, "reason", "") == "human_review_required":
                raise AgentHumanReview("browser dialog requires human review") from None
            raise AgentTaskError("managed WebRunner observation failed") from None
        elements: list[dict] = []
        self._elements(elements, raw.get("elements", []), "")
        for frame in raw.get("frames", []):
            self._elements(elements, frame.get("elements", []), frame["selector"])
        return {"identity": {"browser_session": self._identity, "url": raw.get("url", "")},
                "title": raw.get("title", ""), "text": raw.get("text", ""), "elements": elements,
                "semantic_observation": True, "text_redacted": True}

    @staticmethod
    def _elements(result: list[dict], values: list[dict], frame: str) -> None:
        for value in values:
            result.append({"index": len(result), "selector": value["selector"], "frame": frame,
                           "name": value.get("text", ""), "role": value.get("role") or value.get("tag", ""),
                           "enabled": value.get("is_enabled", False), "visible": value.get("is_visible", False)})

    def perform(self, name: str, arguments: dict) -> Any:
        """Use the shared command authority gates, with the session bound only for this dispatch."""
        if self._readonly is not None:
            raise AgentTaskError("read-only browser cannot perform tools")
        if name not in BROWSER_ADAPTER_TOOLS or self._session is None:
            raise AgentTaskError("command is outside the reviewed browser adapter")
        from je_auto_control.utils.tool_use_schema import run_tool_call
        with browser_session_scope(self._session):
            return run_tool_call(name, arguments)

    def cleanup(self) -> None:
        """Acknowledge only successful SDK retirement; the host still reaps its owned helper tree."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:  # noqa: BLE001 - retain the SDK owner on failed cleanup
                raise AgentTaskError("managed browser cleanup is unconfirmed") from None
            self._session = None
            self._spec = None

    def verify_browser(self, clause: Mapping[str, Any]) -> bool:
        """Check only a criterion pinned in this session's task, using fresh explicit SDK reads."""
        if self._spec is None or self._session is None or clause not in self._spec.success_criteria:
            raise AgentTaskError("browser verification criterion is outside the owned task")
        from je_auto_control.utils.agent_runtime.browser_verification import evaluate_browser_clause
        try:
            return evaluate_browser_clause(self.readonly_spec, self._session, clause)
        except (AutoControlException, CancelledError):
            raise
        except Exception:  # noqa: BLE001 - SDK URL/read failures must not expose raw browser data
            raise AgentTaskError("managed browser verification is unavailable") from None

    def validate_input(self, _event: dict) -> None:
        """Browser sessions grant no native mouse, keyboard, clipboard or file-dialog access."""
        raise AgentTaskError("browser tasks cannot drive native desktop input")
