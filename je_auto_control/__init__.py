"""
import all wrapper function
"""

# callback
from je_auto_control.utils.callback.callback_function_executor import \
    callback_executor
# Critical
from je_auto_control.utils.critical_exit.critical_exit import CriticalExit
from je_auto_control.utils.cv2_utils.screen_record import ScreenRecorder
# utils cv2_utils
from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
# Recording
from je_auto_control.utils.cv2_utils.video_recording import RecordingThread
from je_auto_control.utils.exception.exceptions import \
    AutoControlActionException
from je_auto_control.utils.exception.exceptions import \
    AutoControlActionNullException
from je_auto_control.utils.exception.exceptions import \
    AutoControlCantFindKeyException
# Exception
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.exceptions import \
    AutoControlJsonActionException
from je_auto_control.utils.exception.exceptions import \
    AutoControlKeyboardException
from je_auto_control.utils.exception.exceptions import \
    AutoControlMouseException
from je_auto_control.utils.exception.exceptions import \
    AutoControlRecordException
from je_auto_control.utils.exception.exceptions import \
    AutoControlScreenException
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.executor.action_executor import \
    add_command_to_executor
# executor
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.executor.action_executor import \
    execute_action_with_vars
from je_auto_control.utils.executor.action_executor import execute_files
from je_auto_control.utils.executor.action_executor import executor
# Accessibility (headless)
from je_auto_control.utils.accessibility import (
    AccessibilityElement, AccessibilityNotAvailableError,
    AccessibilityRecorder, AXRecorderEvent, AXTreeNode,
    click_accessibility_element, control_get_value, control_invoke,
    control_set_value, control_toggle, dump_accessibility_tree,
    find_accessibility_element, list_accessibility_elements,
    read_control_table,
)
# VLM element locator (headless)
from je_auto_control.utils.vision import (
    VLMNotAvailableError, click_by_description, locate_by_description,
    verify_description,
)
# Self-healing locator (image template first, VLM fallback, audit log)
from je_auto_control.utils.self_healing import (
    HealEvent, HealEventLog, HealOutcome, SelfHealError,
    default_heal_log, self_heal_click, self_heal_locate,
)
# Screenshot PII redaction (blur regions before VLM upload / audit log).
from je_auto_control.utils.redaction import (
    POLICY_MODERATE, POLICY_OFF, POLICY_STRICT,
    RedactionEngine, RedactionPolicy, RedactionResult,
    default_policy as default_redaction_policy,
    policy_from_name as redaction_policy_from_name,
    redact_png_bytes,
)
# Screenshot annotation (draw boxes / highlights / arrows / labels).
from je_auto_control.utils.annotate import annotate_screenshot
# Cross-platform desktop notifications.
from je_auto_control.utils.notify import NotifyResult, notify
# Region colour statistics (dominant / average colour).
from je_auto_control.utils.color_stats import ColorStats, region_color_stats
# Per-window capture, window-layout save / restore, snap/tile.
from je_auto_control.utils.window_capture import (
    capture_window, get_window_geometry, restore_window_layout,
    save_window_layout, snap_window,
)
# Scroll until a target image / text is visible.
from je_auto_control.utils.scroll_find import scroll_until_visible
# Recoverable deletion (move files to the OS recycle bin).
from je_auto_control.utils.trash import move_to_trash
# QR code decoding from a screen region / image.
from je_auto_control.utils.qr import read_qr_codes
# WebRunner bridge (headless: optional je_web_runner dependency)
from je_auto_control.utils.webrunner_bridge import (
    WebRunnerBridgeError, is_webrunner_available, list_webrunner_commands,
    run_webrunner_action, run_webrunner_actions,
    web_current_url, web_open, web_quit, web_screenshot,
)
# Clipboard (headless)
from je_auto_control.utils.clipboard.clipboard import (
    get_clipboard, set_clipboard,
)
# Hotkey daemon (headless)
from je_auto_control.utils.hotkey.hotkey_daemon import (
    HotkeyBinding, HotkeyDaemon, default_hotkey_daemon,
)
# OTP/TOTP for automated 2FA logins
from je_auto_control.utils.otp import (
    TOTPError, generate_secret, generate_totp, verify_totp,
)
# Native file Open/Save/folder dialog helper
from je_auto_control.utils.file_dialog import (
    FileDialogDriver, handle_file_dialog,
)
# Locked / non-interactive session guard
from je_auto_control.utils.session_guard import (
    ensure_interactive_session, is_session_locked,
)
# Transactional work queue (dispatcher/performer)
from je_auto_control.utils.work_queue import (
    BusinessError, WorkItem, WorkQueue,
)
# Seeded synthetic test-data generation
from je_auto_control.utils.test_data import generate_rows, write_dataset
# Risk-based test selection from run history
from je_auto_control.utils.test_select import rank_flows, select_flows
# MCP registry server.json manifest
from je_auto_control.utils.mcp_registry import (
    build_server_manifest, write_server_manifest,
)
# Named locator repository (object repository) for native UI
from je_auto_control.utils.element_repository import ElementRepository
# Step-through debugger / tracer for action lists
from je_auto_control.utils.flow_debugger import FlowDebugger, trace_actions
# Persistent library of reusable action sequences (skills/playbooks)
from je_auto_control.utils.skill_library import Skill, SkillLibrary
# Heuristic prompt-injection guardrail for untrusted on-screen text
from je_auto_control.utils.guardrail import (
    assess_text, redact_text, scan_text,
)
# A2A (agent-to-agent) agent card
from je_auto_control.utils.a2a import build_agent_card, write_agent_card
# Headless Office I/O (optional [office] extra: openpyxl/python-docx/pptx)
from je_auto_control.utils.office import (
    read_document, read_presentation, read_workbook,
    write_document, write_presentation, write_workbook,
)
# Persistent episodic memory for agents (goal -> trajectory -> outcome)
from je_auto_control.utils.agent_memory import AgentMemory, Episode
# Deterministic run controls (seeded RNG + frozen wall clock)
from je_auto_control.utils.deterministic import (
    DeterministicRun, seed_everything,
)
# Reactive screen observer (appear / vanish / change -> callback)
from je_auto_control.utils.observer import (
    ScreenObserver, WatchRule, default_observer,
    image_predicate, pixel_predicate, text_predicate,
)
# CycloneDX SBOM generation (supply-chain compliance)
from je_auto_control.utils.sbom import build_sbom, write_sbom
# Duration-aware suite sharding + shard-result merge
from je_auto_control.utils.test_shard import merge_results, shard_flows
# Data-quality: row schema validation, field extraction, masking
from je_auto_control.utils.data_quality import (
    extract_fields, mask_rows, validate_rows,
)
# i18n / l10n testing: pseudo-localize, overflow + catalog checks
from je_auto_control.utils.i18n_test import (
    check_catalog, check_overflow, pseudo_localize, pseudo_localize_catalog,
)
# Flow checkpoint & resume (durable execution for long action lists)
from je_auto_control.utils.checkpoint import (
    Checkpoint, CheckpointStore, run_resumable,
)
# Set-of-Marks overlay (number elements for VLM grounding)
from je_auto_control.utils.set_of_marks import (
    mark_click, mark_elements, mark_screen, render_marks, resolve_mark,
)
# Semantic screen state (snapshot/diff + structured description)
from je_auto_control.utils.screen_state import (
    describe_screen, diff_snapshots, screen_changed, snapshot,
    snapshot_screen,
)
# Timed input replay + declarative input-sequence DSL
from je_auto_control.utils.input_macro import replay_timeline, run_sequence
# Resilience primitives (retry-with-backoff + circuit breaker)
from je_auto_control.utils.resilience import (
    CircuitBreaker, CircuitOpenError, RetryPolicy, retry_call,
)
# CI workflow annotations (GitHub Actions)
from je_auto_control.utils.ci_annotations import (
    emit_annotations, format_annotation,
)
# Clipboard history (ring buffer + background poller)
from je_auto_control.utils.clipboard_history import (
    ClipboardHistory, default_clipboard_history,
)
# Self-heal analytics + action-secrets scanning (audit/analysis)
from je_auto_control.utils.heal_analytics import analyze_heal_log, heal_stats
from je_auto_control.utils.secrets_scan import scan_secrets
# Process-documentation (SOP) generator from an action list
from je_auto_control.utils.process_doc import (
    describe_step, generate_sop, write_sop,
)
# Eased / tweened interpolated drag
from je_auto_control.utils.tween_drag import (
    easing_names, tween_drag, tween_points,
)
# Plugin SDK: discover/load third-party AC_* commands via entry points
from je_auto_control.utils.plugin_sdk import (
    COMMANDS_GROUP, discover_plugins, load_plugins,
)
# Maker-checker approval gate + just-in-time credential leases (PAM/governance)
from je_auto_control.utils.governance import (
    ApprovalGate, CredentialBroker, CredentialBrokerError, default_broker,
    set_secret_resolver,
)
# Network egress allowlist guard for the headless HTTP client
from je_auto_control.utils.egress import (
    EgressBlocked, EgressPolicy, get_egress_policy, set_egress_policy,
)
# Approval testing: verify artifacts against a human-approved baseline
from je_auto_control.utils.approval import (
    ApprovalResult, approve_artifact, pending_artifacts, verify_artifact,
)
# Agent trajectory evaluation: score a recorded run against a rubric
from je_auto_control.utils.trajectory_eval import evaluate_trajectory
# Compliance: map governance evidence to SOC2 / ISO 27001 controls
from je_auto_control.utils.compliance import (
    build_compliance_report, render_compliance_html, write_compliance_report,
)
# Agent observability: OpenTelemetry GenAI-convention spans
from je_auto_control.utils.agent_trace import (
    AgentTrace, default_trace, reset_trace,
)
# Video step-overlay report: caption screenshots into a walkthrough video
from je_auto_control.utils.video_report import (
    VideoStep, build_overlay_plan, render_overlay_frame, write_step_video,
)
# Fuzzy string matching / dedupe (difflib default, optional rapidfuzz)
from je_auto_control.utils.fuzzy import (
    fuzzy_best_match, fuzzy_dedupe, fuzzy_matches, fuzzy_ratio,
)
# S3-compatible artifact store (optional boto3, injectable client)
from je_auto_control.utils.artifact_store import (
    S3ArtifactStore, configure_default_store, get_default_store,
    set_default_store,
)
# Perceptual-hash image dedupe (Pillow aHash/dHash)
from je_auto_control.utils.image_dedup import (
    average_hash, dedupe_images, dhash, hamming_distance, images_similar,
)
# Locale-aware number/currency/date parsing & formatting (optional babel)
from je_auto_control.utils.locale_parse import (
    format_currency, format_date, format_decimal, parse_decimal, parse_number,
)
# Voice-command router (injectable speech-to-text)
from je_auto_control.utils.voice import (
    VoiceCommand, VoiceRouter, default_voice_router,
)
# Coordinate-space mapping (model grid <-> physical pixels)
from je_auto_control.utils.coordinate_space import (
    CoordinateSpace, downscale_png, normalized_space, xga_space,
)
# Mechanical stuck-loop detection for agent loops
from je_auto_control.utils.loop_guard import (
    LoopGuard, LoopVerdict, default_loop_guard, digest_result,
)
# Task/process mining: automation-candidate discovery from action logs
from je_auto_control.utils.process_mining import (
    Candidate, MiningReport, SequencePattern, directly_follows,
    find_repeated_sequences, mine_action_log, rank_automation_candidates,
)
# Background popup/interrupt watchdog (unattended automation)
from je_auto_control.utils.watchdog import (
    PopupWatchdog, WatchdogRule, default_popup_watchdog,
)
# OCR (headless)
from je_auto_control.utils.ocr.ocr_engine import (
    TextMatch, click_text, find_text_matches, find_text_regex,
    locate_text_center, read_text_in_region, set_tesseract_cmd,
    wait_for_text,
)
# LLM action planner (headless)
from je_auto_control.utils.llm import (
    LLMBackend, LLMNotAvailableError, LLMPlanError,
    plan_actions, run_from_description,
)
# Agent loop + production backends (headless)
from je_auto_control.utils.agent.agent_loop import (
    AgentBackend, AgentBudget, AgentLoop, AgentResult, AgentStep,
    FakeAgentBackend, run_agent,
)
from je_auto_control.utils.agent.backends import (
    AgentBackendError, AnthropicAgentBackend, ComputerUseAgentBackend,
    OpenAIAgentBackend,
)
from je_auto_control.utils.agent.computer_use import (
    result_to_dict as computer_use_result_to_dict,
    run_computer_use,
)
# Cross-host DAG orchestrator
from je_auto_control.utils.dag import (
    DagDefinition, DagDefinitionError, DagNode, DagRunResult,
    NodeResult, parse_dag, run_dag,
)
# Remote-desktop presence (multi-viewer roster + roles)
from je_auto_control.utils.remote_desktop.presence import (
    PresenceError, PresenceRegistry, ROLE_CONTROLLER, ROLE_OBSERVER,
    ViewerPresence, default_presence_registry,
)
# Chat-ops bot (Slack / generic command router)
from je_auto_control.utils.chatops import (
    ChatOpsError, CommandResult, CommandRouter, SlackBot, SlackError,
    make_default_slack_bot, register_chatops_default_commands,
)
# Anchor-based locators (spatial composition of locator backends)
from je_auto_control.utils.anchor_locator import (
    AnchorLocatorError, AnchorOutcome, Locator as AnchorLocator,
    a11y_locator, anchor_locate, image_locator, ocr_locator,
    vlm_locator,
)
# Structured OCR (rows / tables / form fields)
from je_auto_control.utils.ocr.structure import (
    OCRField, OCRRow, OCRTable, StructuredOCR,
    cluster_matches as ocr_cluster_matches,
    read_structure as ocr_read_structure,
)
# Smart waits (frame-diff replacements for time.sleep)
from je_auto_control.utils.smart_waits import (
    WaitOutcome, wait_until_clipboard_changes, wait_until_file,
    wait_until_pixel_changes, wait_until_port, wait_until_process,
    wait_until_region_idle, wait_until_screen_stable, wait_until_window_closed,
)
# Visual regression (golden-image comparison)
from je_auto_control.utils.visual_regression import (
    DiffResult, MaskRegion, compare_to_golden, image_difference, take_golden,
)
# Declarative finite-state-machine engine for action JSON
from je_auto_control.utils.state_machine import (
    StateMachine, StateMachineError, run_state_machine,
)
# Assertion DSL (verify screen state; raise on mismatch)
from je_auto_control.utils.assertion import (
    AssertionResult, GroupAssertionResult, assert_all, assert_any,
    assert_by_description, assert_clipboard, assert_duration,
    assert_eventually, assert_file, assert_http, assert_image, assert_pixel,
    assert_process, assert_text, assert_variable, assert_window,
    run_assertion_spec,
)
# Data-driven execution (load rows from CSV / JSON / SQLite / Excel)
from je_auto_control.utils.data_source import data_source_kinds, load_rows
# Flaky-test detection (analytics over the run-history store)
from je_auto_control.utils.flakiness import (
    FlakinessReport, FlakyEntry, analyze_flakiness,
)
# QA suite orchestration + CI report output (JUnit / Allure)
from je_auto_control.utils.test_suite import (
    TestCaseResult, TestSuiteResult, run_suite,
    to_allure_results, to_junit_xml, write_allure_results, write_junit_xml,
)
# Flaky-test quarantine (skip known-unstable cases)
from je_auto_control.utils.quarantine import (
    QuarantineEntry, QuarantineStore, auto_quarantine_from_flakiness,
    default_quarantine_store,
)
# Accessibility / i18n audit (missing labels, WCAG contrast, truncation)
from je_auto_control.utils.a11y_audit import (
    AuditIssue, AuditReport, audit_contrast, audit_missing_labels,
    audit_target_size, contrast_ratio, detect_truncation, run_audit,
    wcag_audit,
)
# Mobile device matrix (parallel script execution across devices)
from je_auto_control.utils.device_matrix import (
    DeviceResult, MatrixReport, run_on_devices,
)
# Media assertions (audio activity, video motion)
from je_auto_control.utils.media_assert import (
    MediaAssertionResult, assert_audio_activity, assert_video_changes,
    measure_audio_rms, video_segment_motion,
)
# Cost telemetry (per-LLM-call token + USD tracking)
from je_auto_control.utils.cost_telemetry import (
    CostEvent, CostSummary, default_cost_store, estimate_llm_usd,
    record_llm_call, summarise_llm_costs,
)
# Failure → ticket automation (Jira / Linear / GitHub fan-out)
from je_auto_control.utils.failure_hooks import (
    FailureHookManager, FailureReport, GitHubBackend, JiraBackend,
    LinearBackend, TicketResult, default_failure_hook_manager,
)
# A/B locator framework (race N strategies, recommend best)
from je_auto_control.utils.ab_locator import (
    ABRunOutcome, ab_best_strategy, ab_locate, ab_report_for,
    default_ab_store,
)
# Remote desktop (headless)
from je_auto_control.utils.remote_desktop import (
    AuthenticationError as RemoteDesktopAuthError,
    InputDispatchError as RemoteDesktopInputError,
    ProtocolError as RemoteDesktopProtocolError,
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.connect_coordinator import (
    ConnectTarget as RemoteDesktopConnectTarget,
    UnresolvableTargetError as RemoteDesktopUnresolvableTargetError,
    parse_target as parse_remote_desktop_target,
)
from je_auto_control.utils.remote_desktop.registry import (
    registry as remote_desktop_registry,
)
from je_auto_control.utils.gamepad import (
    GamepadUnavailable, VirtualGamepad,
    default_gamepad as default_virtual_gamepad,
    is_available as is_virtual_gamepad_available,
)
# MCP server (headless stdio bridge for Claude / other MCP clients)
from je_auto_control.utils.mcp_server import (
    AuditLogger, HttpMCPServer, MCPContent, MCPPrompt, MCPPromptArgument,
    MCPResource, MCPServer, MCPTool, MCPToolAnnotations,
    OperationCancelledError, PromptProvider, RateLimiter,
    ResourceProvider, ToolCallContext, build_default_tool_registry,
    default_prompt_provider, default_resource_provider,
    make_plugin_tool, register_plugin_tools, start_mcp_http_server,
    start_mcp_stdio_server,
)
# Plugin loader (headless)
from je_auto_control.utils.plugin_loader.plugin_loader import (
    discover_plugin_commands, load_plugin_directory, load_plugin_file,
    register_plugin_commands,
)
# REST API (headless)
from je_auto_control.utils.rest_api.rest_server import (
    RestApiServer, start_rest_api_server,
)
# Admin console (headless multi-host client)
from je_auto_control.utils.admin import (
    AdminConsoleClient, AdminHost, default_admin_console,
)
# WebRTC inspector (headless rolling stats history)
from je_auto_control.utils.remote_desktop.webrtc_inspector import (
    WebRTCInspector, default_webrtc_inspector,
)
# USB device enumeration + hotplug + passthrough Phase 2a (read-only on
# the wire by default — passthrough opcode dispatch needs an explicit
# opt-in via enable_usb_passthrough() or JE_AUTOCONTROL_USB_PASSTHROUGH=1)
from je_auto_control.utils.usb import (
    UsbAcl, UsbDevice, UsbEnumerationResult, UsbEvent, UsbHotplugWatcher,
    UsbPassthroughClient, UsbPassthroughSession, default_usb_watcher,
    enable_usb_passthrough, is_usb_passthrough_enabled, list_usb_devices,
)
# System diagnostics (headless self-test)
from je_auto_control.utils.diagnostics import (
    Check, DiagnosticsReport, run_diagnostics,
)
# Config bundle (export / import user configuration)
from je_auto_control.utils.config_bundle import (
    ConfigBundleExporter, ConfigBundleImporter, ImportReport,
    export_config_bundle, import_config_bundle,
)
# Profiler (headless)
from je_auto_control.utils.profiler import (
    ActionProfiler, ActionStats, default_profiler,
)
# Secrets (headless)
from je_auto_control.utils.secrets import (
    SecretManager, SecretStoreError, SecretStoreLocked,
    default_secret_manager, default_secret_store_path,
)
# Action-file security (HMAC-SHA256 sign/verify + Fernet encrypt, headless)
from je_auto_control.utils.action_signing import (
    VerifyResult, decrypt_action_file, encrypt_action_file,
    require_signed_actions, sign_action_file, verify_action_file,
)
# Observability (Prometheus metrics + OpenTelemetry traces, headless)
from je_auto_control.utils.observability import (
    Counter as MetricCounter,
    Gauge as MetricGauge,
    Histogram as MetricHistogram,
    MetricRegistry, PrometheusExporter, Tracer,
    default_exporter as default_metrics_exporter,
    default_registry as default_metric_registry,
    default_tracer, render_metrics_text, traced,
)
# Run history (headless)
from je_auto_control.utils.run_history.history_store import (
    HistoryStore, RunRecord, default_history_store,
)
# Triggers (headless)
from je_auto_control.utils.triggers.trigger_engine import (
    AllOfTrigger, AnyOfTrigger, CronTrigger, FilePathTrigger,
    ImageAppearsTrigger, PixelColorTrigger, SequenceTrigger, TriggerEngine,
    WindowAppearsTrigger, default_trigger_engine,
)
from je_auto_control.utils.triggers.webhook_server import (
    WebhookTrigger, WebhookTriggerServer, default_webhook_server,
)
from je_auto_control.utils.triggers.email_trigger import (
    EmailTrigger, EmailTriggerWatcher, default_email_trigger_watcher,
)
# Recording editor (headless helpers)
from je_auto_control.utils.recording_edit.editor import (
    adjust_delays, dedupe_moves, filter_actions, insert_action,
    merge_sleeps, remove_action, scale_coordinates, trim_actions,
)
# Scheduler (headless)
from je_auto_control.utils.scheduler.scheduler import (
    ScheduledJob, Scheduler, default_scheduler,
)
# Script variables (headless)
from je_auto_control.utils.script_vars.interpolate import (
    interpolate_actions, interpolate_value, load_vars_from_json,
)
from je_auto_control.utils.script_vars.scope import VariableScope
# Watchers (headless)
from je_auto_control.utils.watcher.watcher import (
    LogTail, MouseWatcher, PixelWatcher,
)
# file process
from je_auto_control.utils.file_process.get_dir_file_list import \
    get_dir_files_as_list
# html report
from je_auto_control.utils.generate_report.generate_html_report import \
    generate_html
from je_auto_control.utils.generate_report.generate_html_report import \
    generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import \
    generate_json
from je_auto_control.utils.generate_report.generate_json_report import \
    generate_json_report
# xml
from je_auto_control.utils.generate_report.generate_xml_report import \
    generate_xml
from je_auto_control.utils.generate_report.generate_xml_report import \
    generate_xml_report
# json
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.json.json_file import write_action_json
from je_auto_control.utils.json.json_file import format_action_json
# codegen: action list -> pytest / python / robot source
from je_auto_control.utils.codegen.codegen import (
    generate_code,
    generate_code_file,
)
# HTTP/API request action (dependency-free, stdlib urllib)
from je_auto_control.utils.http_client.http_client import http_request
# Ad-hoc read-only SQL query against SQLite
from je_auto_control.utils.sql.sql_query import query_sqlite
# Send email via SMTP
from je_auto_control.utils.email_send.email_sender import send_email
# PDF document text extraction + assertion (optional pypdf backend)
from je_auto_control.utils.pdf.pdf_reader import (
    assert_pdf_text, extract_pdf_text, pdf_metadata, pdf_page_count,
)
# package manager
from je_auto_control.utils.package_manager.package_manager_class import \
    package_manager
from je_auto_control.utils.project.create_project_structure import \
    create_project_dir
# Shell command
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.shell_process.shell_exec import default_shell_manager
# socket server
from je_auto_control.utils.socket_server.auto_control_socket_server import \
    start_autocontrol_socket_server
# Start exe
from je_auto_control.utils.start_exe.start_another_process import start_exe
# test record
from je_auto_control.utils.test_record.record_test_class import \
    test_record_instance
from je_auto_control.wrapper.auto_control_image import locate_all_image
from je_auto_control.wrapper.auto_control_image import locate_and_click
from je_auto_control.wrapper.auto_control_image import locate_image_center
# Keyboard wrappers
from je_auto_control.wrapper.auto_control_keyboard import check_key_is_press
from je_auto_control.wrapper.auto_control_keyboard import get_keyboard_keys_table
from je_auto_control.wrapper.auto_control_keyboard import hotkey
from je_auto_control.wrapper.auto_control_keyboard import keyboard_keys_table
from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key
from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key
from je_auto_control.wrapper.auto_control_keyboard import send_key_event_to_window
from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
from je_auto_control.wrapper.auto_control_keyboard import write
# Mouse wrappers
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
from je_auto_control.wrapper.auto_control_mouse import mouse_keys_table
from je_auto_control.wrapper.auto_control_mouse import mouse_scroll
from je_auto_control.wrapper.auto_control_mouse import mouse_scroll_error_message
from je_auto_control.wrapper.auto_control_mouse import press_mouse
from je_auto_control.wrapper.auto_control_mouse import release_mouse
from je_auto_control.wrapper.auto_control_mouse import send_mouse_event_to_window
from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
from je_auto_control.wrapper.auto_control_mouse import special_mouse_keys_table
# Human-like input: motion + typing (headless)
from je_auto_control.utils.humanize.motion import (
    HumanizedMotion, humanized_path, move_mouse_humanized,
)
from je_auto_control.utils.humanize.typing import (
    humanized_key_delays, type_text_humanized,
)
# record
from je_auto_control.wrapper.auto_control_record import record
from je_auto_control.wrapper.auto_control_record import stop_record
from je_auto_control.wrapper.auto_control_record import record_to_json
# Screen wrappers
from je_auto_control.wrapper.auto_control_screen import screen_size
from je_auto_control.wrapper.auto_control_screen import screenshot
from je_auto_control.wrapper.auto_control_screen import get_pixel
# Cross-platform window manager (headless)
from je_auto_control.wrapper.auto_control_window import (
    close_window_by_title, find_window, focus_window, list_windows,
    show_window_by_title, wait_for_window,
)
# Windows-only modules (ctypes.WINFUNCTYPE / Win32 API) — gated so
# ``import je_auto_control`` keeps working on macOS / Linux. Kept last
# so every preceding statement is a plain top-level import (ruff E402).
import sys as _sys_for_platform_check  # noqa: E402
if _sys_for_platform_check.platform in ("win32", "cygwin", "msys"):
    from je_auto_control.windows.window import windows_window_manage  # noqa: E402
else:
    windows_window_manage = None  # type: ignore[assignment]
del _sys_for_platform_check


def start_autocontrol_gui(*args, **kwargs):
    """Launch the GUI (imports PySide6 lazily so headless usage stays Qt-free)."""
    from je_auto_control.gui import start_autocontrol_gui as _impl
    return _impl(*args, **kwargs)

__all__ = [
    "click_mouse", "mouse_keys_table", "get_mouse_position", "press_mouse", "release_mouse",
    "mouse_scroll", "mouse_scroll_error_message", "set_mouse_position", "special_mouse_keys_table",
    "HumanizedMotion", "humanized_path", "move_mouse_humanized",
    "humanized_key_delays", "type_text_humanized",
    "keyboard_keys_table", "press_keyboard_key", "release_keyboard_key", "type_keyboard", "check_key_is_press",
    "write", "hotkey", "start_exe", "get_keyboard_keys_table",
    "screen_size", "screenshot", "locate_all_image", "locate_image_center", "locate_and_click",
    "CriticalExit", "AutoControlException", "AutoControlKeyboardException",
    "AutoControlMouseException", "AutoControlCantFindKeyException",
    "AutoControlScreenException", "ImageNotFoundException", "AutoControlJsonActionException",
    "AutoControlRecordException", "AutoControlActionNullException", "AutoControlActionException", "record",
    "stop_record", "read_action_json", "write_action_json", "format_action_json",
    "execute_action", "execute_files", "executor",
    "execute_action_with_vars", "record_to_json",
    "generate_code", "generate_code_file", "http_request", "query_sqlite",
    "send_email", "assert_pdf_text", "extract_pdf_text", "pdf_metadata",
    "pdf_page_count",
    "add_command_to_executor", "test_record_instance", "pil_screenshot",
    # OCR
    "TextMatch", "find_text_matches", "locate_text_center", "wait_for_text",
    "click_text", "set_tesseract_cmd", "read_text_in_region",
    "find_text_regex",
    # Recording editor
    "trim_actions", "insert_action", "remove_action", "filter_actions",
    "adjust_delays", "scale_coordinates", "dedupe_moves", "merge_sleeps",
    # Scheduler
    "Scheduler", "ScheduledJob", "default_scheduler",
    # Script variables
    "interpolate_actions", "interpolate_value", "load_vars_from_json",
    "VariableScope",
    # Watchers
    "MouseWatcher", "PixelWatcher", "LogTail",
    # Window manager
    "list_windows", "find_window", "focus_window", "wait_for_window",
    "close_window_by_title", "show_window_by_title",
    # Clipboard
    "get_clipboard", "set_clipboard",
    # Hotkey daemon
    "HotkeyDaemon", "HotkeyBinding", "default_hotkey_daemon",
    "PopupWatchdog", "WatchdogRule", "default_popup_watchdog",
    "generate_totp", "verify_totp", "generate_secret", "TOTPError",
    "handle_file_dialog", "FileDialogDriver",
    "ensure_interactive_session", "is_session_locked",
    "WorkQueue", "WorkItem", "BusinessError",
    "generate_rows", "write_dataset",
    "rank_flows", "select_flows",
    "build_server_manifest", "write_server_manifest",
    "ElementRepository",
    "FlowDebugger", "trace_actions",
    "Skill", "SkillLibrary",
    "assess_text", "redact_text", "scan_text",
    "build_agent_card", "write_agent_card",
    "read_workbook", "write_workbook",
    "read_document", "write_document",
    "read_presentation", "write_presentation",
    "AgentMemory", "Episode",
    "DeterministicRun", "seed_everything",
    "ScreenObserver", "WatchRule", "default_observer",
    "image_predicate", "pixel_predicate", "text_predicate",
    "build_sbom", "write_sbom",
    "merge_results", "shard_flows",
    "extract_fields", "mask_rows", "validate_rows",
    "check_catalog", "check_overflow", "pseudo_localize",
    "pseudo_localize_catalog",
    "Checkpoint", "CheckpointStore", "run_resumable",
    "mark_click", "mark_elements", "mark_screen", "render_marks",
    "resolve_mark",
    "describe_screen", "diff_snapshots", "screen_changed", "snapshot",
    "snapshot_screen",
    "replay_timeline", "run_sequence",
    "CircuitBreaker", "CircuitOpenError", "RetryPolicy", "retry_call",
    "emit_annotations", "format_annotation",
    "ClipboardHistory", "default_clipboard_history",
    "analyze_heal_log", "heal_stats", "scan_secrets",
    "describe_step", "generate_sop", "write_sop",
    "easing_names", "tween_drag", "tween_points",
    "COMMANDS_GROUP", "discover_plugins", "load_plugins",
    "ApprovalGate", "CredentialBroker", "CredentialBrokerError",
    "default_broker", "set_secret_resolver",
    "EgressBlocked", "EgressPolicy", "get_egress_policy", "set_egress_policy",
    "ApprovalResult", "approve_artifact", "pending_artifacts",
    "verify_artifact",
    "evaluate_trajectory",
    "build_compliance_report", "render_compliance_html",
    "write_compliance_report",
    "AgentTrace", "default_trace", "reset_trace",
    "VideoStep", "build_overlay_plan", "render_overlay_frame",
    "write_step_video",
    "fuzzy_best_match", "fuzzy_dedupe", "fuzzy_matches", "fuzzy_ratio",
    "S3ArtifactStore", "configure_default_store", "get_default_store",
    "set_default_store",
    "average_hash", "dedupe_images", "dhash", "hamming_distance",
    "images_similar",
    "format_currency", "format_date", "format_decimal", "parse_decimal",
    "parse_number",
    "VoiceCommand", "VoiceRouter", "default_voice_router",
    "CoordinateSpace", "downscale_png", "normalized_space", "xga_space",
    "LoopGuard", "LoopVerdict", "default_loop_guard", "digest_result",
    "Candidate", "MiningReport", "SequencePattern", "directly_follows",
    "find_repeated_sequences", "mine_action_log",
    "rank_automation_candidates",
    # MCP server
    "AuditLogger", "HttpMCPServer", "MCPContent", "MCPPrompt",
    "MCPPromptArgument", "MCPResource", "MCPServer", "MCPTool",
    "MCPToolAnnotations", "OperationCancelledError", "PromptProvider",
    "RateLimiter", "ResourceProvider", "ToolCallContext",
    "build_default_tool_registry",
    "default_prompt_provider", "default_resource_provider",
    "make_plugin_tool", "register_plugin_tools",
    "start_mcp_http_server", "start_mcp_stdio_server",
    # Plugin loader
    "load_plugin_file", "load_plugin_directory", "discover_plugin_commands",
    "register_plugin_commands",
    # REST API
    "RestApiServer", "start_rest_api_server",
    # Admin console
    "AdminConsoleClient", "AdminHost", "default_admin_console",
    # WebRTC inspector
    "WebRTCInspector", "default_webrtc_inspector",
    # USB enumeration + hotplug + passthrough Phase 2a/2a.1/40
    "UsbDevice", "UsbEnumerationResult", "list_usb_devices",
    "UsbEvent", "UsbHotplugWatcher", "default_usb_watcher",
    "UsbPassthroughSession", "UsbPassthroughClient",
    "UsbAcl",
    "enable_usb_passthrough", "is_usb_passthrough_enabled",
    # System diagnostics
    "Check", "DiagnosticsReport", "run_diagnostics",
    # Config bundle
    "ConfigBundleExporter", "ConfigBundleImporter", "ImportReport",
    "export_config_bundle", "import_config_bundle",
    # Triggers
    "TriggerEngine", "default_trigger_engine",
    "ImageAppearsTrigger", "WindowAppearsTrigger",
    "PixelColorTrigger", "FilePathTrigger",
    "AllOfTrigger", "AnyOfTrigger", "SequenceTrigger", "CronTrigger",
    "WebhookTrigger", "WebhookTriggerServer", "default_webhook_server",
    "EmailTrigger", "EmailTriggerWatcher",
    "default_email_trigger_watcher",
    # Profiler
    "ActionProfiler", "ActionStats", "default_profiler",
    # Secret manager
    "SecretManager", "SecretStoreError", "SecretStoreLocked",
    "default_secret_manager", "default_secret_store_path",
    # Action-file security (sign + encrypt)
    "VerifyResult", "sign_action_file", "verify_action_file",
    "require_signed_actions", "encrypt_action_file", "decrypt_action_file",
    # Observability (Prometheus + OpenTelemetry)
    "MetricCounter", "MetricGauge", "MetricHistogram",
    "MetricRegistry", "default_metric_registry",
    "PrometheusExporter", "default_metrics_exporter", "render_metrics_text",
    "Tracer", "default_tracer", "traced",
    # Run history
    "HistoryStore", "RunRecord", "default_history_store",
    # Accessibility
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "AccessibilityRecorder", "AXRecorderEvent", "AXTreeNode",
    "click_accessibility_element", "dump_accessibility_tree",
    "find_accessibility_element", "list_accessibility_elements",
    "control_get_value", "control_set_value", "control_invoke",
    "control_toggle", "read_control_table",
    # VLM locator
    "VLMNotAvailableError", "locate_by_description", "click_by_description",
    "verify_description",
    # LLM action planner
    "LLMBackend", "LLMNotAvailableError", "LLMPlanError",
    "plan_actions", "run_from_description",
    # Agent loop + production backends
    "AgentBackend", "AgentBudget", "AgentLoop", "AgentResult", "AgentStep",
    "FakeAgentBackend", "run_agent",
    "AgentBackendError", "AnthropicAgentBackend", "ComputerUseAgentBackend",
    "OpenAIAgentBackend",
    "run_computer_use", "computer_use_result_to_dict",
    # DAG orchestrator
    "DagDefinition", "DagDefinitionError", "DagNode", "DagRunResult",
    "NodeResult", "parse_dag", "run_dag",
    # Multi-viewer presence
    "PresenceError", "PresenceRegistry", "ROLE_CONTROLLER",
    "ROLE_OBSERVER", "ViewerPresence", "default_presence_registry",
    # Chat-ops bot
    "ChatOpsError", "CommandResult", "CommandRouter", "SlackBot",
    "SlackError", "make_default_slack_bot",
    "register_chatops_default_commands",
    # Anchor-based locator
    "AnchorLocator", "AnchorLocatorError", "AnchorOutcome",
    "a11y_locator", "anchor_locate", "image_locator", "ocr_locator",
    "vlm_locator",
    # Structured OCR
    "OCRField", "OCRRow", "OCRTable", "StructuredOCR",
    "ocr_cluster_matches", "ocr_read_structure",
    # Smart waits
    "WaitOutcome", "wait_until_pixel_changes",
    "wait_until_region_idle", "wait_until_screen_stable",
    "wait_until_clipboard_changes", "wait_until_window_closed",
    "wait_until_file", "wait_until_port", "wait_until_process",
    # Visual regression + state machine
    "take_golden", "compare_to_golden", "image_difference",
    "DiffResult", "MaskRegion",
    "run_state_machine", "StateMachine", "StateMachineError",
    # Assertion DSL
    "AssertionResult", "assert_image", "assert_pixel",
    "assert_text", "assert_window", "assert_clipboard", "assert_process",
    "assert_file", "assert_http", "assert_by_description", "assert_duration",
    "assert_variable",
    # Assertion combinators (soft groups + eventual polling)
    "GroupAssertionResult", "assert_all", "assert_any", "assert_eventually",
    "run_assertion_spec",
    # Data-driven execution
    "data_source_kinds", "load_rows",
    # Flaky-test detection
    "FlakinessReport", "FlakyEntry", "analyze_flakiness",
    # QA suite orchestration + CI reports
    "TestCaseResult", "TestSuiteResult", "run_suite",
    "to_allure_results", "to_junit_xml",
    "write_allure_results", "write_junit_xml",
    # Flaky quarantine
    "QuarantineEntry", "QuarantineStore",
    "auto_quarantine_from_flakiness", "default_quarantine_store",
    # Accessibility / i18n audit
    "AuditIssue", "AuditReport", "audit_contrast", "audit_missing_labels",
    "audit_target_size", "contrast_ratio", "detect_truncation", "run_audit",
    "wcag_audit",
    # Mobile device matrix
    "DeviceResult", "MatrixReport", "run_on_devices",
    # Media assertions
    "MediaAssertionResult", "assert_audio_activity", "assert_video_changes",
    "measure_audio_rms", "video_segment_motion",
    # Cost telemetry
    "CostEvent", "CostSummary", "default_cost_store",
    "estimate_llm_usd", "record_llm_call", "summarise_llm_costs",
    # Failure → ticket
    "FailureHookManager", "FailureReport", "GitHubBackend",
    "JiraBackend", "LinearBackend", "TicketResult",
    "default_failure_hook_manager",
    # A/B locator framework
    "ABRunOutcome", "ab_best_strategy", "ab_locate",
    "ab_report_for", "default_ab_store",
    # Self-healing locator (image → VLM fallback)
    "HealEvent", "HealEventLog", "HealOutcome", "SelfHealError",
    "default_heal_log", "self_heal_click", "self_heal_locate",
    # Screenshot redaction (PII blur)
    "POLICY_MODERATE", "POLICY_OFF", "POLICY_STRICT",
    "RedactionEngine", "RedactionPolicy", "RedactionResult",
    "default_redaction_policy", "redaction_policy_from_name",
    "redact_png_bytes",
    # Screenshot annotation
    "annotate_screenshot",
    # Desktop notifications
    "NotifyResult", "notify",
    # Region colour statistics
    "ColorStats", "region_color_stats",
    # Per-window capture + window-layout save / restore + snap
    "capture_window", "get_window_geometry",
    "save_window_layout", "restore_window_layout", "snap_window",
    # Scroll-to-find
    "scroll_until_visible",
    # Recoverable deletion (recycle bin)
    "move_to_trash",
    # QR code decoding
    "read_qr_codes",
    # WebRunner bridge (browser automation via je_web_runner)
    "WebRunnerBridgeError", "is_webrunner_available",
    "list_webrunner_commands", "run_webrunner_action",
    "run_webrunner_actions", "web_current_url", "web_open",
    "web_quit", "web_screenshot",
    # Remote desktop
    "RemoteDesktopHost", "RemoteDesktopViewer",
    "RemoteDesktopAuthError", "RemoteDesktopInputError",
    "RemoteDesktopProtocolError", "remote_desktop_registry",
    "RemoteDesktopConnectTarget", "RemoteDesktopUnresolvableTargetError",
    "parse_remote_desktop_target",
    # Virtual gamepad (ViGEm)
    "VirtualGamepad", "GamepadUnavailable",
    "default_virtual_gamepad", "is_virtual_gamepad_available",
    "generate_html", "generate_html_report", "generate_json", "generate_json_report", "generate_xml",
    "generate_xml_report", "get_dir_files_as_list", "create_project_dir", "start_autocontrol_socket_server",
    "callback_executor", "package_manager", "ShellManager", "default_shell_manager",
    "RecordingThread", "send_key_event_to_window", "send_mouse_event_to_window", "windows_window_manage",
    "ScreenRecorder", "get_pixel",
    "start_autocontrol_gui"
]
