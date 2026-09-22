"""MCP adapters for running work: agents, governance, telemetry and test operations.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
import threading
from typing import Any, Dict, List, Optional



#: Where approval artefacts are written when the caller names no directory.
_DEFAULT_APPROVALS_DIR = ".approvals"

#: Named token buckets shared by every ``rate_limit`` call.
_RATE_LIMITERS: Dict[str, Any] = {}
_RATE_LIMITERS_LOCK = threading.Lock()


def watchdog_add(title, action="close", case_sensitive=False, name=None):
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.add_window_rule(
        title, action=action, case_sensitive=bool(case_sensitive), name=name)
    return {"rules": default_popup_watchdog.rule_names()}


def watchdog_start():
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.start()
    return {"running": True}


def watchdog_stop():
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.stop()
    return {"running": False}


def watchdog_list():
    from je_auto_control.utils.watchdog import default_popup_watchdog
    w = default_popup_watchdog
    return {"running": w.running, "rules": w.rule_names(), "hits": w.hits}


def generate_otp(secret, step=30, digits=6):
    from je_auto_control.utils.otp import generate_totp
    return generate_totp(secret, step=int(step), digits=int(digits))


def assert_session_active():
    from je_auto_control.utils.session_guard import ensure_interactive_session
    return {"interactive": ensure_interactive_session()}


def _work_queue(db, name):
    from je_auto_control.utils.work_queue import WorkQueue
    return WorkQueue(db, name)


def generate_data(schema, count=10, path=None, fmt=None, seed=None):
    from je_auto_control.utils.test_data import generate_rows, write_dataset
    rows = generate_rows(schema, int(count), seed=seed)
    if path:
        return {"path": write_dataset(rows, path, fmt), "count": len(rows)}
    return {"rows": rows, "count": len(rows)}


def mcp_manifest(path=None, include_tools=False):
    from je_auto_control.utils.mcp_registry import (
        build_server_manifest, write_server_manifest)
    if path:
        return {"path": write_server_manifest(
            path, include_tools=bool(include_tools))}
    return {"manifest": build_server_manifest(
        include_tools=bool(include_tools))}


def rank_tests(flows, history_path=None, window=10):
    from je_auto_control.utils.test_select import rank_flows
    return {"ranked": rank_flows(flows, history_path=history_path,
                                 window=int(window))}


def select_tests(flows, k=None, threshold=None, history_path=None, window=10):
    from je_auto_control.utils.test_select import select_flows
    return {"selected": select_flows(
        flows, k=k, threshold=threshold, history_path=history_path,
        window=int(window))}


def debug_trace(actions, dry_run=False):
    from je_auto_control.utils.flow_debugger import trace_actions
    return {"trace": trace_actions(actions, dry_run=bool(dry_run))}


def _skill_lib(path):
    from je_auto_control.utils.skill_library import SkillLibrary
    return SkillLibrary(path)


def guard_text(text, threshold=2):
    from je_auto_control.utils.guardrail import assess_text
    return assess_text(text, threshold=int(threshold))


def agent_card(path=None):
    from je_auto_control.utils.a2a import build_agent_card, write_agent_card
    if path:
        return {"path": write_agent_card(path)}
    return {"card": build_agent_card()}


def _agent_memory(db):
    from je_auto_control.utils.agent_memory import AgentMemory
    return AgentMemory(db)


def seed_everything(seed=0):
    from je_auto_control.utils.deterministic import seed_everything as _seed
    return {"seed": _seed(int(seed))}


def generate_sbom(path=None, root="je_auto_control"):
    from je_auto_control.utils.sbom import build_sbom, write_sbom
    root_arg = root or None
    if path:
        return {"path": write_sbom(path, root_arg)}
    return {"sbom": build_sbom(root_arg)}


def shard_suite(flows, shards=2, history_path=None, window=20):
    from je_auto_control.utils.test_shard import shard_flows
    return {"shards": shard_flows(flows, int(shards),
                                  history_path=history_path,
                                  window=int(window))}


def merge_results(reports):
    from je_auto_control.utils.test_shard import merge_results as _merge
    return _merge(reports)


def validate_rows(rows, schema):
    from je_auto_control.utils.data_quality import validate_rows as _validate
    return _validate(rows, schema)


def extract_fields(text, fields=None, patterns=None):
    from je_auto_control.utils.data_quality import extract_fields as _extract
    return {"fields": _extract(text, fields=fields, patterns=patterns)}


def mask_rows(rows, rules):
    from je_auto_control.utils.data_quality import mask_rows as _mask
    return {"rows": _mask(rows, rules)}


def run_resumable(actions, run_id, db, variables=None):
    from je_auto_control.utils.checkpoint import (
        CheckpointStore, run_resumable as _run)
    return _run(actions, run_id=run_id, store=CheckpointStore(db),
                variables=variables)


def checkpoint_status(run_id, db):
    from je_auto_control.utils.checkpoint import CheckpointStore
    cp = CheckpointStore(db).load(run_id)
    if cp is None:
        return {"checkpoint": None}
    return {"checkpoint": {"run_id": cp.run_id, "step_index": cp.step_index,
                           "variables": cp.variables}}


def checkpoint_clear(run_id, db):
    from je_auto_control.utils.checkpoint import CheckpointStore
    return {"cleared": CheckpointStore(db).clear(run_id)}


def ci_annotations(annotations):
    from je_auto_control.utils.ci_annotations import emit_annotations
    return {"lines": emit_annotations(annotations)}


def scan_secrets(data):
    from je_auto_control.utils.secrets_scan import scan_secrets as _scan
    return {"findings": _scan(data)}


def list_plugins(group="je_auto_control.commands"):
    from je_auto_control.utils.plugin_sdk import discover_plugins
    return {"commands": sorted(discover_plugins(group))}


def load_plugins(group="je_auto_control.commands"):
    from je_auto_control.utils.plugin_sdk import load_plugins as _load
    return {"loaded": _load(group)}


def approval_request(action: str, requester: str = "",
                     db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    return {"token": ApprovalGate(db).request(action, requester)}


def approval_approve(token: str, approver: str, db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    return {"approved": ApprovalGate(db).approve(token, approver)}


def approval_reject(token: str, approver: str, db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    return {"rejected": ApprovalGate(db).reject(token, approver)}


def approval_status(token: str, db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    gate = ApprovalGate(db)
    return {"status": gate.status(token), "approved": gate.is_approved(token)}


def lease_secret(name: str, ttl: float = 300.0):
    from je_auto_control.utils.governance import default_broker
    return {"token": default_broker.lease(name, ttl), "ttl": float(ttl)}


def lease_valid(token: str):
    from je_auto_control.utils.governance import default_broker
    return {"valid": default_broker.is_valid(token)}


def revoke_lease(token: str):
    from je_auto_control.utils.governance import default_broker
    return {"revoked": default_broker.revoke(token)}


def lease_active():
    from je_auto_control.utils.governance import default_broker
    return {"leases": default_broker.active()}


def egress_allow(allow=None, deny=None):
    from je_auto_control.utils.egress import set_egress_policy
    policy = set_egress_policy(allow, deny)
    return {"allow": policy.allow, "deny": policy.deny}


def egress_check(url: str):
    from je_auto_control.utils.egress import get_egress_policy
    return {"allowed": get_egress_policy().is_allowed(url)}


def egress_reset():
    from je_auto_control.utils.egress import set_egress_policy
    set_egress_policy(None, None)
    return {"allow": None, "deny": []}


def verify_artifact(name: str, content, approvals_dir: str = _DEFAULT_APPROVALS_DIR,
                    extension: str = "txt"):
    from je_auto_control.utils.approval import verify_artifact as _verify
    result = _verify(name, content, approvals_dir, extension)
    return {"status": result.status, "match": result.match,
            "approved_path": result.approved_path,
            "received_path": result.received_path}


def approve_artifact(name: str, approvals_dir: str = _DEFAULT_APPROVALS_DIR,
                     extension: str = "txt"):
    from je_auto_control.utils.approval import approve_artifact as _approve
    return {"approved": _approve(name, approvals_dir, extension)}


def pending_artifacts(approvals_dir: str = _DEFAULT_APPROVALS_DIR):
    from je_auto_control.utils.approval import pending_artifacts as _pending
    return {"pending": _pending(approvals_dir)}


def evaluate_trajectory(trajectory, rubric):
    from je_auto_control.utils.trajectory_eval import (
        evaluate_trajectory as _evaluate)
    return _evaluate(trajectory, rubric)


def compliance_report(evidence, frameworks=None, path=None, fmt="json"):
    from je_auto_control.utils.compliance import (
        build_compliance_report, write_compliance_report)
    report = build_compliance_report(evidence, frameworks)
    if path:
        report["path"] = write_compliance_report(report, path, fmt)
    return report


def trace_record(operation, model=None, system=None, input_tokens=None,
                 output_tokens=None, tool_name=None, duration_s=0.0,
                 status="ok"):
    from je_auto_control.utils.agent_trace import default_trace
    return default_trace.record(
        operation, model=model, system=system, input_tokens=input_tokens,
        output_tokens=output_tokens, tool_name=tool_name,
        duration_s=duration_s, status=status)


def trace_summary():
    from je_auto_control.utils.agent_trace import default_trace
    return default_trace.summary()


def trace_export():
    from je_auto_control.utils.agent_trace import default_trace
    return {"spans": default_trace.to_otel()}


def trace_reset():
    from je_auto_control.utils.agent_trace import reset_trace
    reset_trace()
    return {"reset": True}


def write_step_video(steps, output, fps=10, seconds_per_step=2.0):
    from je_auto_control.utils.video_report import (
        write_step_video as _write)
    return _write(steps, output, fps=fps, seconds_per_step=seconds_per_step)


def s3_upload(local_path, key=None):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"key": get_default_store().upload(local_path, key)}


def s3_download(key, local_path):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"path": get_default_store().download(key, local_path)}


def s3_list(prefix=None):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"keys": get_default_store().list(prefix)}


def s3_delete(key):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"deleted": get_default_store().delete(key)}


def loop_guard_observe(tool, args=None, result_digest=""):
    from je_auto_control.utils.loop_guard import default_loop_guard
    verdict = default_loop_guard.observe(tool, args, result_digest)
    return {"pattern": verdict.pattern, "level": verdict.level,
            "count": verdict.count}


def loop_guard_reset():
    from je_auto_control.utils.loop_guard import default_loop_guard
    default_loop_guard.reset()
    return {"reset": True}


def mine_actions(actions, min_len=2, max_len=5, min_count=3):
    from je_auto_control.utils.process_mining import mine_action_log
    report = mine_action_log(actions, min_len=min_len, max_len=max_len,
                             min_count=min_count)
    return {
        "total_actions": report.total_actions,
        "patterns": [{"actions": list(p.actions), "count": p.count}
                     for p in report.patterns],
        "candidates": [{"actions": list(c.pattern.actions),
                        "count": c.pattern.count, "score": c.score}
                       for c in report.candidates],
    }


def set_asset(name, value, asset_type="text", environment="default", db=None):
    from je_auto_control.utils.assets.assets import store_set
    return store_set(name, value, asset_type=asset_type,
                     environment=environment, db=db)


def get_asset(name, environment="default", db=None):
    from je_auto_control.utils.assets.assets import store_get
    return store_get(name, environment=environment, db=db)


def list_assets(environment=None, db=None):
    from je_auto_control.utils.assets.assets import store_list
    return store_list(environment=environment, db=db)


def emit_event(event_type, data=None, source="je_auto_control",
               subject=None, url=None):
    from je_auto_control.utils.events import post_cloudevent, to_cloudevent
    event = to_cloudevent(event_type, source, data, subject=subject)
    result: Dict[str, Any] = {"event": event}
    if url:
        result["status"] = post_cloudevent(url, event)
    return result


def notify_webhook(url, text, transport="raw", title=None):
    from je_auto_control.utils.notify_channels import (
        notify_webhook as _notify)
    outcome = _notify(url, text, transport=transport, title=title)
    return {"ok": outcome.ok, "status": outcome.status,
            "transport": outcome.transport}


def scan_vulns(components, advisories=None):
    from je_auto_control.utils.vuln_scan import scan_components
    if isinstance(components, dict):
        components = components.get("components", [])
    findings = scan_components(components, advisories or [])
    return {"findings": findings, "count": len(findings)}


def apply_vex(findings, vex):
    from je_auto_control.utils.vex import apply_vex as _apply
    kept = _apply(findings, vex)
    return {"findings": kept, "count": len(kept)}


def check_licenses(components, allow=None, deny=None):
    from je_auto_control.utils.license_policy import evaluate_sbom
    if isinstance(components, dict):
        components = components.get("components", [])
    violations = evaluate_sbom(components, allow=allow, deny=deny)
    return {"violations": violations, "count": len(violations)}


def jwt_encode(claims, key, alg="HS256"):
    from je_auto_control.utils.jwt import encode_jwt
    return {"token": encode_jwt(claims, key, alg=alg)}


def jwt_decode(token, key, algorithms=None, audience=None, leeway=0.0):
    from je_auto_control.utils.jwt import ClaimsPolicy, JwtError, decode_jwt
    policy = ClaimsPolicy(algorithms=tuple(algorithms) if algorithms
                          else ("HS256",), audience=audience, leeway=leeway)
    try:
        claims = decode_jwt(token, key, policy)
    except JwtError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "claims": claims}


def rate_limit(name, rate=1.0, capacity=1.0, n=1.0):
    from je_auto_control.utils.rate_limit import TokenBucket
    rate = float(rate)
    capacity = float(capacity)
    with _RATE_LIMITERS_LOCK:
        existing = _RATE_LIMITERS.get(name)
        # setdefault silently ignored a changed rate/capacity for a reused
        # name; rebuild the bucket when either parameter differs so the caller
        # actually gets the limit they asked for.
        if existing is None or existing[0] != rate or existing[1] != capacity:
            bucket = TokenBucket(rate, capacity)
            _RATE_LIMITERS[name] = (rate, capacity, bucket)
        else:
            bucket = existing[2]
    acquired = bucket.try_acquire(float(n))
    return {"acquired": acquired, "tokens": round(bucket.tokens, 4),
            "wait": round(bucket.time_until_available(float(n)), 4)}


def describe_stats(values):
    from je_auto_control.utils.stats import describe
    return describe(values)


def ab_significance(a_conv, a_n, b_conv, b_n):
    from je_auto_control.utils.stats import two_proportion_z_test
    return two_proportion_z_test(int(a_conv), int(a_n), int(b_conv), int(b_n))


def evaluate_slo(records, target, window_s=None):
    from je_auto_control.utils.slo import evaluate_slo as _slo
    return _slo(records, float(target), window_s=window_s)


def burn_alerts(records, target):
    from je_auto_control.utils.slo import burn_alerts as _alerts
    alerts = _alerts(records, float(target))
    return {"alerts": alerts, "firing": bool(alerts)}


def percentiles(samples, qs=None):
    from je_auto_control.utils.percentiles import exact_percentiles
    result = exact_percentiles(samples, qs=tuple(qs) if qs else (50, 90, 95, 99))
    return {"percentiles": {str(q): value for q, value in result.items()}}


def retry_after(response):
    from je_auto_control.utils.bulkhead import next_delay
    return {"delay": next_delay(response)}


def http_replay(cassette, url, method="GET"):
    from je_auto_control.utils.http_cassette import Cassette
    interactions = (cassette.get("interactions", [])
                    if isinstance(cassette, dict) else cassette)
    response = Cassette(interactions).replay(
        {"method": str(method).upper(), "url": url})
    return {"response": response}


def build_provenance(paths, builder_id="je_auto_control"):
    from je_auto_control.utils.provenance import build_provenance, subject_for
    subjects = [subject_for(path) for path in paths]
    return {"statement": build_provenance(subjects, builder_id=builder_id)}


def verify_provenance(statement, files):
    from je_auto_control.utils.provenance import verify_provenance as _verify
    mismatches = _verify(statement, files)
    return {"ok": not mismatches, "mismatches": mismatches}


def evaluate_flag(flags, key, context=None):
    from je_auto_control.utils.feature_flags import (
        FlagStore, evaluate_flag as _ev)
    store = FlagStore.from_dict(flags) if isinstance(flags, dict) else flags
    return _ev(store, key, context or {})


def flag_enabled(flags, key, context=None, default=False):
    from je_auto_control.utils.feature_flags import FlagStore, is_enabled
    store = FlagStore.from_dict(flags) if isinstance(flags, dict) else flags
    return {"enabled": is_enabled(store, key, context or {}, bool(default))}


def run_saga(steps):
    from je_auto_control.utils.saga import run_saga as _run
    result = _run(steps)
    return {"ok": result.ok, "completed": result.completed,
            "compensated": result.compensated,
            "failed_step": result.failed_step, "error": result.error}


def decision_table(spec, context):
    from je_auto_control.utils.decision_table import evaluate_table
    return {"result": evaluate_table(spec, context)}


def export_sarif(findings, path=None, tool_name="AutoControl"):
    from je_auto_control.utils.sarif import to_sarif, write_sarif
    result: Dict[str, Any] = {"sarif": to_sarif(findings, tool_name=tool_name)}
    if path:
        result["path"] = write_sarif(findings, path, tool_name=tool_name)
    return result


def run_dag(definition: Dict[str, Any],
            max_parallel: int = 4) -> Dict[str, Any]:
    from je_auto_control.utils.dag import run_dag as _run_dag
    return _run_dag(definition, max_parallel=int(max_parallel)).to_dict()


def failure_hook_fire(source: str, source_id: str,
                       error_text: str = "",
                       script_path: Optional[str] = None,
                       screenshot_path: Optional[str] = None,
                       log_tail: str = "",
                       metadata: Optional[Dict[str, Any]] = None,
                       ) -> List[Dict[str, Any]]:
    from je_auto_control.utils.failure_hooks import (
        FailureReport, default_failure_hook_manager,
    )
    report = FailureReport(
        source=source, source_id=source_id, error_text=error_text,
        script_path=script_path, screenshot_path=screenshot_path,
        log_tail=log_tail, metadata=dict(metadata or {}),
    )
    return [result.to_dict()
            for result in default_failure_hook_manager.fire(report)]


def failure_hook_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.failure_hooks import default_failure_hook_manager
    return default_failure_hook_manager.list_backends()


def costs_record(provider: str, model: str,
                  input_tokens: int, output_tokens: int,
                  label: Optional[str] = None,
                  run_id: Optional[str] = None,
                  user: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.cost_telemetry import record_llm_call
    return record_llm_call(
        provider=provider, model=model,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        label=label, run_id=run_id, user=user,
    ).to_dict()


def costs_summary(limit: int = 10000) -> Dict[str, Any]:
    from je_auto_control.utils.cost_telemetry import (
        default_cost_store, summarise_llm_costs,
    )
    events = default_cost_store.list_events(limit=int(limit))
    return summarise_llm_costs(events).to_dict()


def costs_list(limit: int = 100) -> List[Dict[str, Any]]:
    from je_auto_control.utils.cost_telemetry import default_cost_store
    return [event.to_dict()
            for event in default_cost_store.list_events(limit=int(limit))]


def chatops_dispatch(message: str,
                     context: Optional[Dict[str, Any]] = None,
                     script_root: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.chatops import (
        CommandRouter, register_chatops_default_commands,
    )
    router = CommandRouter()
    register_chatops_default_commands(router)
    merged: Dict[str, Any] = dict(context or {})
    if script_root is not None:
        merged.setdefault("script_root", script_root)
    result = router.dispatch(message, context=merged)
    return {"matched": False} if result is None else {
        "matched": True, **result.to_dict(),
    }


def computer_use(goal: str,
                 display_width_px: Optional[int] = None,
                 display_height_px: Optional[int] = None,
                 display_number: Optional[int] = None,
                 max_steps: int = 25,
                 wall_seconds: float = 300.0,
                 model: str = "claude-opus-4-7",
                 max_tokens: int = 1024) -> Dict[str, Any]:
    from je_auto_control.utils.agent.computer_use import (
        result_to_dict, run_computer_use,
    )
    result = run_computer_use(
        goal,
        display_width_px=display_width_px,
        display_height_px=display_height_px,
        display_number=display_number,
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
        model=model, max_tokens=int(max_tokens),
    )
    return result_to_dict(result)
