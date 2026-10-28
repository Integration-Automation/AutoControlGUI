"""Public automation exports, resolved from their original owners on first access."""
import sys as _sys
from typing import TYPE_CHECKING as _TYPE_CHECKING

from je_auto_control._export_bindings import EXPORTS as _EXPORTS
from je_auto_control._lazy_exports import resolve_export as _resolve_export


if _TYPE_CHECKING:
    from je_auto_control.utils.agent_runtime import (
        browser_navigate,
        browser_click,
        browser_fill,
        browser_select,
        browser_check,
        browser_read,
        browser_wait,
        browser_link,
        browser_download,
        browser_upload,
        draft_agent_workflow,
        workflow_download,
        workflow_manifest,
        workflow_control,
        workflow_open,
        workflow_wait,
        AgentActionRequest,
        AgentActionResult,
        AgentControlBusy,
        AgentObservation,
        AgentRuntime,
        AgentTaskBudget,
        AgentTaskError,
        AgentTaskHandle,
        AgentTaskResult,
        AgentTaskSpec,
        get_agent_task_receipts,
        reconcile_agent_task,
        prune_agent_tasks,
        manage_agent_trigger,
        list_agent_triggers,
        recover_agent_target,
        manage_agent_transfer,
        manage_agent_skill,
        list_agent_skills,
        manage_agent_recovery,
        AgentObservationStale,
        AgentHumanReview,
        AgentTargetProfile,
        manage_agent_target,
        list_agent_targets,
        act_agent_task,
        agent_runtime_status,
        cancel_agent_task,
        finish_agent_task,
        get_agent_task,
        lookup_agent_task,
        inspect_agent_dag,
        manage_agent_dag,
        list_agent_tasks,
        observe_agent_task,
        pause_agent_task,
        resume_agent_task,
        start_agent_runtime,
        stop_agent_runtime,
        submit_agent_task,
        stop_all_agent_tasks,
    )
    from je_auto_control.utils.callback.callback_function_executor import callback_executor
    from je_auto_control.utils.critical_exit.critical_exit import CriticalExit
    from je_auto_control.utils.cv2_utils.screen_record import ScreenRecorder
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    from je_auto_control.utils.cv2_utils.video_recording import RecordingThread
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.utils.exception.exceptions import (
        AutoControlActionNullException,
    )
    from je_auto_control.utils.exception.exceptions import (
        AutoControlCantFindKeyException,
    )
    from je_auto_control.utils.exception.exceptions import AutoControlException
    from je_auto_control.utils.exception.exceptions import (
        AutoControlJsonActionException,
    )
    from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException
    from je_auto_control.utils.exception.exceptions import AutoControlMouseException
    from je_auto_control.utils.exception.exceptions import AutoControlRecordException
    from je_auto_control.utils.exception.exceptions import AutoControlScreenException
    from je_auto_control.utils.exception.exceptions import (
        AutoControlFlatTemplateException,
    )
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    from je_auto_control.utils.executor.action_executor import add_command_to_executor
    from je_auto_control.utils.executor.action_executor import execute_action
    from je_auto_control.utils.executor.action_executor import execute_action_with_vars
    from je_auto_control.utils.executor.action_executor import execute_files
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.accessibility import (
        AccessibilityElement,
        accessibility_status,
        AccessibilityNotAvailableError,
        AccessibilityRecorder,
        AXRecorderEvent,
        AXTreeNode,
        click_accessibility_element,
        control_get_state,
        control_get_value,
        control_invoke,
        control_set_value,
        control_toggle,
        dump_accessibility_tree,
        find_accessibility_element,
        find_accessibility_elements,
        focused_accessibility_element,
        list_accessibility_elements,
        read_control_table,
    )
    from je_auto_control.utils.control_patterns import (
        collapse_control,
        control_expand_state,
        control_range,
        expand_control,
        scroll_control_into_view,
        select_control_item,
        set_control_range,
    )
    from je_auto_control.utils.ax_text import (
        control_text_attributes,
        find_control_text,
        get_control_text,
        get_selected_text,
        get_visible_text,
        select_control_text,
    )
    from je_auto_control.utils.ax_tree_walk import (
        assign_node_paths,
        control_type_name,
        find_by_path,
        humanize_role,
        humanize_tree,
    )
    from je_auto_control.utils.focus_order import (
        audit_focus_order,
        focus_control,
        is_interactive_role,
        tab_order,
    )
    from je_auto_control.utils.virtualized import realize_item
    from je_auto_control.utils.ax_props import (
        get_element_properties,
        is_element_enabled,
    )
    from je_auto_control.utils.table_pattern import (
        cell_by_header,
        table_cell,
        table_headers,
    )
    from je_auto_control.utils.transform_window import (
        move_element,
        resize_element,
        set_window_state,
        window_interaction_state,
    )
    from je_auto_control.utils.legacy_accessible import (
        legacy_default_action,
        legacy_info,
    )
    from je_auto_control.utils.selection_view import (
        get_selection,
        list_views,
        set_view,
    )
    from je_auto_control.utils.ax_events import wait_for_focus_change
    from je_auto_control.utils.shell_open import open_path, plan_open
    from je_auto_control.utils.idle_keepawake import (
        allow_sleep,
        idle_seconds,
        is_idle,
        keep_awake,
        keep_awake_on,
        plan_keep_awake,
    )
    from je_auto_control.utils.file_assoc import file_association, normalize_ext
    from je_auto_control.utils.system_volume import (
        change_volume,
        get_volume,
        is_muted,
        mute,
        set_mute,
        set_volume,
        toggle_mute,
        unmute,
    )
    from je_auto_control.utils.lock_session import (
        classify_lock_transitions,
        lock_session,
        plan_lock_session,
        wait_for_lock,
        wait_for_unlock,
    )
    from je_auto_control.utils.ime_state import (
        decode_conversion_mode,
        ime_state,
        is_composing,
        wait_for_composition_commit,
    )
    from je_auto_control.utils.retry_budget import (
        RetryBudget,
        backoff_delay,
        jittered_delay,
        run_with_budget,
    )
    from je_auto_control.utils.verify_field import (
        compare_field_value,
        fill_and_verify,
        verify_field_value,
    )
    from je_auto_control.utils.adaptive_timeout import (
        recommend_timeout,
        timeout_stats,
    )
    from je_auto_control.utils.ensure_state import ensure_state, ensure_toggle
    from je_auto_control.utils.app_idle import idle_point, wait_until_app_idle
    from je_auto_control.utils.cvd_simulate import (
        color_distance,
        colors_collide,
        simulate_cvd,
    )
    from je_auto_control.utils.marks_layout import label_color, place_labels
    from je_auto_control.utils.contrast_map import (
        dominant_pair,
        grade_contrast,
        region_contrast,
    )
    from je_auto_control.utils.theme_normalize import match_theme, normalize_theme
    from je_auto_control.utils.change_localize import localize_changes, rank_changes
    from je_auto_control.utils.icon_classify import (
        box_features,
        classify_icon,
        classify_widget,
    )
    from je_auto_control.utils.element_proposal import propose_elements, tag_kinds
    from je_auto_control.utils.act_in_view import ScrollPlan, act_in_view
    from je_auto_control.utils.act_modes import act_with_mode
    from je_auto_control.utils.clipboard_rich_formats import (
        build_rtf,
        csv_to_rows,
        get_clipboard_csv,
        get_clipboard_rtf,
        rows_to_csv,
        rtf_to_text,
        set_clipboard_csv,
        set_clipboard_rtf,
    )
    from je_auto_control.utils.clipboard_formats import (
        classify_format,
        classify_formats,
        clipboard_formats,
        diff_formats,
        list_clipboard_formats,
    )
    from je_auto_control.utils.file_drop import drop_files, plan_file_drop
    from je_auto_control.utils.image_quality import (
        image_quality,
        is_blurry,
        quality_gate,
    )
    from je_auto_control.utils.scale_detect import detect_scale, scale_sweep
    from je_auto_control.utils.saliency import (
        most_salient,
        salient_regions,
        saliency_map,
    )
    from je_auto_control.utils.failure_signature import (
        failure_signature,
        group_failures,
        normalize_error,
    )
    from je_auto_control.utils.run_diff import diff_runs, summarize_run_diff
    from je_auto_control.utils.flake_cluster import (
        cofailure_pairs,
        failure_clusters,
    )
    from je_auto_control.utils.step_timeline import build_timeline, critical_steps
    from je_auto_control.utils.vision import (
        VLMNotAvailableError,
        click_by_description,
        locate_by_description,
        verify_description,
    )
    from je_auto_control.utils.self_healing import (
        HealEvent,
        HealEventLog,
        HealOutcome,
        SelfHealError,
        default_heal_log,
        self_heal_click,
        self_heal_locate,
        SelfHealRequest,
        SelfHealRequestError,
        SelfHealRunResult,
        SelfHealVerificationError,
        VerificationRequest,
        self_heal_run,
        inspect_heal_source,
        create_template_candidate,
        preview_template_candidate,
        verify_template_candidate,
        accept_template_candidate,
        revert_template_candidate,
        TemplateCandidateState,
        TemplateCandidatePreview,
        TemplateCandidateVerification,
        TemplateCandidateTransition,
        TemplateRevisionError,
        TemplateRevisionConflict,
        EvaluationRatio,
        EvaluationSample,
        HealingAttempt,
        HealingComparison,
        HealingEvaluationError,
        HealingVersionReport,
        LocatorCandidate,
        LocatorStrategy,
        TemplateFrameLocator,
        VLMFrameLocator,
        evaluate_healing_manifest,
        evaluate_locators,
        write_healing_report,
    )
    from je_auto_control.utils.redaction import (
        POLICY_MODERATE,
        POLICY_OFF,
        POLICY_STRICT,
        RedactionEngine,
        RedactionPolicy,
        RedactionResult,
        default_policy as default_redaction_policy,
        policy_from_name as redaction_policy_from_name,
        redact_png_bytes,
    )
    from je_auto_control.utils.annotate import annotate_screenshot
    from je_auto_control.utils.notify import NotifyResult, notify
    from je_auto_control.utils.color_stats import ColorStats, region_color_stats
    from je_auto_control.utils.window_capture import (
        arrange_cascade,
        arrange_grid,
        capture_window,
        get_window_geometry,
        restore_window_layout,
        save_window_layout,
        snap_window,
    )
    from je_auto_control.utils.scroll_find import scroll_until_visible
    from je_auto_control.utils.trash import move_to_trash
    from je_auto_control.utils.qr import read_qr_codes
    from je_auto_control.utils.webrunner_bridge import (
        WebRunnerBridgeError,
        is_webrunner_available,
        list_webrunner_commands,
        run_webrunner_action,
        run_webrunner_actions,
        web_current_url,
        web_open,
        web_quit,
        web_screenshot,
    )
    from je_auto_control.utils.clipboard.clipboard import (
        get_clipboard,
        get_clipboard_image,
        set_clipboard,
        set_clipboard_image,
    )
    from je_auto_control.utils.hotkey.hotkey_daemon import (
        HotkeyBinding,
        HotkeyDaemon,
        default_hotkey_daemon,
    )
    from je_auto_control.utils.otp import (
        TOTPError,
        generate_secret,
        generate_totp,
        verify_totp,
    )
    from je_auto_control.utils.file_dialog import (
        FileDialogDriver,
        handle_file_dialog,
    )
    from je_auto_control.utils.session_guard import (
        ensure_interactive_session,
        is_session_locked,
    )
    from je_auto_control.utils.work_queue import (
        BusinessError,
        WorkItem,
        WorkQueue,
        WorkQueueError,
    )
    from je_auto_control.utils.test_data import generate_rows, write_dataset
    from je_auto_control.utils.test_select import rank_flows, select_flows
    from je_auto_control.utils.mcp_registry import (
        build_server_manifest,
        write_server_manifest,
    )
    from je_auto_control.utils.element_repository import ElementRepository
    from je_auto_control.utils.flow_debugger import FlowDebugger, trace_actions
    from je_auto_control.utils.skill_library import Skill, SkillLibrary
    from je_auto_control.utils.guardrail import (
        assess_text,
        redact_text,
        scan_text,
    )
    from je_auto_control.utils.a2a import build_agent_card, write_agent_card
    from je_auto_control.utils.office import (
        read_document,
        read_presentation,
        read_workbook,
        write_document,
        write_presentation,
        write_workbook,
    )
    from je_auto_control.utils.agent_memory import AgentMemory, Episode
    from je_auto_control.utils.deterministic import (
        DeterministicRun,
        seed_everything,
    )
    from je_auto_control.utils.observer import (
        ScreenObserver,
        WatchRule,
        default_observer,
        image_predicate,
        pixel_predicate,
        text_predicate,
    )
    from je_auto_control.utils.sbom import build_sbom, write_sbom
    from je_auto_control.utils.test_shard import merge_results, shard_flows
    from je_auto_control.utils.data_quality import (
        extract_fields,
        mask_rows,
        validate_rows,
    )
    from je_auto_control.utils.data_profile import infer_schema, profile_rows
    from je_auto_control.utils.data_drift import (
        categorical_drift,
        detect_drift,
        ks_two_sample,
        psi,
    )
    from je_auto_control.utils.schema_compat import (
        SchemaChange,
        check_compatibility,
        diff_schemas,
        is_backward_compatible,
        is_forward_compatible,
        is_full_compatible,
    )
    from je_auto_control.utils.dataset_diff import (
        cell_changes,
        diff_rows,
        summarize_diff,
    )
    from je_auto_control.utils.referential import (
        check_accepted_values,
        check_foreign_key,
        check_row_count,
        check_unique_key,
    )
    from je_auto_control.utils.i18n_test import (
        check_catalog,
        check_overflow,
        pseudo_localize,
        pseudo_localize_catalog,
    )
    from je_auto_control.utils.checkpoint import (
        Checkpoint,
        CheckpointStore,
        CheckpointStoreError,
        run_resumable,
    )
    from je_auto_control.utils.set_of_marks import (
        mark_click,
        mark_elements,
        mark_screen,
        render_marks,
        resolve_mark,
    )
    from je_auto_control.utils.screen_state import (
        describe_screen,
        diff_snapshots,
        screen_changed,
        snapshot,
        snapshot_screen,
    )
    from je_auto_control.utils.input_macro import replay_timeline, run_sequence
    from je_auto_control.utils.resilience import (
        CircuitBreaker,
        CircuitOpenError,
        RetryPolicy,
        retry_call,
    )
    from je_auto_control.utils.idempotency import (
        IdempotencyConflict,
        IdempotencyStore,
        request_fingerprint,
    )
    from je_auto_control.utils.dedup_window import DedupWindow
    from je_auto_control.utils.sequence_gap import SequenceTracker
    from je_auto_control.utils.optimistic import (
        VersionConflict,
        VersionedStore,
        check_if_match,
        if_match_header,
    )
    from je_auto_control.utils.outbox import Outbox
    from je_auto_control.utils.locale_collation import collation_key, sort_strings
    from je_auto_control.utils.locale_collation import compare as collation_compare
    from je_auto_control.utils.confusables import (
        detect_homoglyphs,
        is_confusable,
        is_mixed_script,
        scripts_of,
    )
    from je_auto_control.utils.confusables import skeleton as confusable_skeleton
    from je_auto_control.utils.readability import (
        automated_readability_index,
        count_syllables,
        flesch_kincaid_grade,
        flesch_reading_ease,
        gunning_fog,
        readability_report,
        readability_stats,
        smog_index,
    )
    from je_auto_control.utils.bidi_check import (
        base_direction,
        bidi_controls,
        detect_bidi_issues,
        has_bidi_controls,
        is_trojan_source,
        strip_bidi_controls,
    )
    from je_auto_control.utils.bidi_check import is_balanced as is_bidi_balanced
    from je_auto_control.utils.list_format import format_list
    from je_auto_control.utils.message_format import (
        format_message,
        ordinal_category,
        plural_category,
    )
    from je_auto_control.utils.gettext_catalog import (
        GettextCatalog,
        parse_po,
        parse_po_file,
        read_mo,
        read_mo_file,
    )
    from je_auto_control.utils.checksum import (
        damm_check_digit,
        damm_validate,
        luhn_check_digit,
        luhn_validate,
        mod97_10_check_digits,
        mod97_10_validate,
        verhoeff_check_digit,
        verhoeff_validate,
    )
    from je_auto_control.utils.mouse_path import (
        drag_path,
        move_along_path,
        path_easings,
        plan_path,
    )
    from je_auto_control.utils.field_entry import plan_field_set, set_field_text
    from je_auto_control.utils.key_hold import hold_key, plan_key_hold
    from je_auto_control.utils.mouse_relative import (
        move_mouse_relative,
        relative_target,
    )
    from je_auto_control.utils.text_unicode import (
        plan_paste,
        plan_unicode_keys,
        type_unicode,
        type_unicode_keys,
        type_unicode_text,
        unicode_code_units,
        unicode_keys_supported,
    )
    from je_auto_control.utils.modifier_state import (
        hold_modifiers,
        plan_with_modifiers,
    )
    from je_auto_control.utils.grid_locator import cluster_grid, locate_cell
    from je_auto_control.utils.visual_match import (
        best_matches,
        match_masked,
        match_masked_all,
        match_template,
        match_template_all,
    )
    from je_auto_control.utils.visual_match import Match as TemplateMatch
    from je_auto_control.utils.rotated_match import (
        RotatedMatch,
        match_rotated,
        match_rotated_all,
        scale_space,
    )
    from je_auto_control.utils.match_trust import (
        TrustedMatch,
        match_with_trust,
        score_peaks,
    )
    from je_auto_control.utils.edge_match import (
        chamfer_distance,
        edge_match,
        edge_match_all,
    )
    from je_auto_control.utils.match_ensemble import match_ensemble, vote_centers
    from je_auto_control.utils.color_match import match_color, match_color_all
    from je_auto_control.utils.match_stability import (
        match_persistence,
        region_stability,
    )
    from je_auto_control.utils.match_autothresh import auto_threshold, match_auto
    from je_auto_control.utils.subpixel_match import (
        SubPixelMatch,
        match_subpixel,
        refine_peak,
    )
    from je_auto_control.utils.screen_grid import (
        GridCell,
        cell_for_point,
        grid_cells,
        point_for_cell,
    )
    from je_auto_control.utils.table_grid_fill import (
        assign_text_to_grid,
        populate_table,
        table_to_csv,
        table_to_records,
    )
    from je_auto_control.utils.observation_delta import (
        delta_index,
        delta_observation,
        summarize_delta,
    )
    from je_auto_control.utils.column_layout import (
        assign_columns,
        column_gutters,
        detect_borderless_table,
        vertical_projection,
    )
    from je_auto_control.utils.reading_flow import flow_order, to_blocks, xy_cut
    from je_auto_control.utils.text_blocks import detect_lists, group_paragraphs
    from je_auto_control.utils.heading_segment import classify_lines, outline
    from je_auto_control.utils.form_fields import (
        associate_fields,
        checkbox_state,
        match_labels_to_widgets,
    )
    from je_auto_control.utils.action_effect import (
        EffectVerdict,
        classify_effect,
        effect_near_point,
        is_no_op,
    )
    from je_auto_control.utils.postcondition import (
        PostconditionReport,
        check_postcondition,
        compile_postcondition,
    )
    from je_auto_control.utils.step_repair import (
        RepairOutcome,
        RepairPolicy,
        next_tactic,
        plan_repair,
        run_with_repair,
    )
    from je_auto_control.utils.grounding_consensus import (
        ConsensusResult,
        consensus_element,
        consensus_point,
        is_confident,
    )
    from je_auto_control.utils.settle_detector import (
        SettleState,
        SettleTracker,
        is_settled,
        settle_point,
    )
    from je_auto_control.utils.critic_features import (
        build_critic_record,
        score_step_rule_based,
        to_judge_prompt,
    )
    from je_auto_control.utils.color_region import (
        find_color_region,
        find_color_regions,
    )
    from je_auto_control.utils.ssim import ssim_changed_regions, ssim_compare
    from je_auto_control.utils.feature_match import feature_match
    from je_auto_control.utils.feature_match import FeatureMatch
    from je_auto_control.utils.shape_locator import find_rectangles, find_shapes
    from je_auto_control.utils.window_layout import (
        WindowRect,
        available_slots,
        cascade_rects,
        grid_rects,
        tile_rect,
    )
    from je_auto_control.utils.preprocess import (
        binarize,
        denoise,
        deskew,
        detect_skew_angle,
        enhance_contrast,
        preprocess_image,
        to_grayscale,
        upscale,
    )
    from je_auto_control.utils.monitor_layout import (
        Monitor,
        enumerate_monitors,
        grab_logical,
        logical_scale,
        logical_virtual_rect,
        monitor_at_point,
        monitor_for_window,
        needs_rescale,
        primary_monitor,
        remap_point,
        to_local,
        to_virtual,
        virtual_bounds,
    )
    from je_auto_control.utils.actionability import (
        ActionabilityReport,
        GateConfig,
        act_when_ready,
        wait_actionable,
    )
    from je_auto_control.utils.element_parse import (
        fuse_elements,
        iou,
        merge_boxes,
        reading_order,
    )
    from je_auto_control.utils.hsv_segment import (
        color_mask,
        dominant_hue_regions,
        segment_hsv,
    )
    from je_auto_control.utils.text_regions import (
        find_text_lines,
        find_text_regions,
    )
    from je_auto_control.utils.edge_lines import (
        find_grid,
        find_lines,
        find_separators,
    )
    from je_auto_control.utils.expect_poll import (
        PollResult,
        assert_poll,
        expect_poll,
        to_be_greater_than,
        to_be_stable,
        to_be_truthy,
        to_contain,
        to_equal,
        to_match_regex,
    )
    from je_auto_control.utils.locator_chain import Candidates, from_boxes
    from je_auto_control.utils.rich_clipboard import (
        build_cf_html,
        get_clipboard_html,
        parse_cf_html,
        set_clipboard_html,
    )
    from je_auto_control.utils.clipboard_files import (
        build_dropfiles,
        get_clipboard_files,
        parse_dropfiles,
        set_clipboard_files,
    )
    from je_auto_control.utils.img_histogram import (
        compare_histograms,
        histogram_changed,
        image_histogram,
    )
    from je_auto_control.utils.motion_regions import (
        activity_score,
        changed_regions,
        has_motion,
    )
    from je_auto_control.utils.window_zorder import (
        bring_to_front,
        plan_zorder,
        send_to_back,
        set_topmost,
    )
    from je_auto_control.utils.soft_assert import (
        SoftAssertions,
        SoftAssertionsFailed,
    )
    from je_auto_control.utils.perceptual_diff import (
        PerceptualDiffResult,
        assert_perceptual,
        perceptual_diff,
    )
    from je_auto_control.utils.window_geometry import (
        client_point,
        client_to_screen,
        frame_insets,
        get_client_rect,
    )
    from je_auto_control.utils.cua_action import (
        canonical_action,
        from_anthropic,
        from_openai_cua,
        to_ac_command,
    )
    from je_auto_control.utils.observation import (
        flatten_tree,
        observation_index,
        serialize_observation,
    )
    from je_auto_control.utils.action_grounding import (
        in_bounds,
        snap_to_element,
        validate_action,
    )
    from je_auto_control.utils.agent_replay import (
        from_jsonl,
        record_step,
        replay_trace,
        to_jsonl,
    )
    from je_auto_control.utils.element_diff import (
        assign_stable_ids,
        match_elements,
    )
    from je_auto_control.utils.element_scoring import (
        ScoredCandidate,
        best_candidate,
        score_candidates,
    )
    from je_auto_control.utils.barcode import read_barcodes
    from je_auto_control.utils.ci_annotations import (
        emit_annotations,
        format_annotation,
    )
    from je_auto_control.utils.clipboard_history import (
        ClipboardHistory,
        default_clipboard_history,
    )
    from je_auto_control.utils.heal_analytics import analyze_heal_log, heal_stats
    from je_auto_control.utils.secrets_scan import scan_secrets
    from je_auto_control.utils.process_doc import (
        describe_step,
        generate_sop,
        write_sop,
    )
    from je_auto_control.utils.tween_drag import (
        easing_names,
        tween_drag,
        tween_points,
    )
    from je_auto_control.utils.plugin_sdk import (
        COMMANDS_GROUP,
        discover_plugins,
        load_plugins,
    )
    from je_auto_control.utils.governance import (
        ApprovalGate,
        CredentialBroker,
        CredentialBrokerError,
        approval_gate,
        default_broker,
        set_secret_resolver,
    )
    from je_auto_control.utils.egress import (
        EgressBlocked,
        EgressPolicy,
        get_egress_policy,
        set_egress_policy,
    )
    from je_auto_control.utils.approval import (
        ApprovalResult,
        approve_artifact,
        pending_artifacts,
        verify_artifact,
    )
    from je_auto_control.utils.trajectory_eval import evaluate_trajectory
    from je_auto_control.utils.compliance import (
        build_compliance_report,
        render_compliance_html,
        write_compliance_report,
    )
    from je_auto_control.utils.agent_trace import (
        AgentTrace,
        default_trace,
        reset_trace,
    )
    from je_auto_control.utils.video_report import (
        VideoStep,
        build_overlay_plan,
        render_overlay_frame,
        write_step_video,
    )
    from je_auto_control.utils.fuzzy import (
        fuzzy_best_match,
        fuzzy_dedupe,
        fuzzy_matches,
        fuzzy_ratio,
    )
    from je_auto_control.utils.text_normalize import (
        deaccent,
        fold_whitespace,
        normalize_quotes,
        normalize_text,
        slugify,
    )
    from je_auto_control.utils.text_similarity import (
        damerau_levenshtein,
        dice,
        jaccard,
        jaro,
        jaro_winkler,
        levenshtein,
        similarity,
    )
    from je_auto_control.utils.near_dup import (
        minhash_signature,
        minhash_similarity,
        near_duplicates,
        simhash,
    )
    from je_auto_control.utils.artifact_store import (
        S3ArtifactStore,
        configure_default_store,
        get_default_store,
        set_default_store,
    )
    from je_auto_control.utils.image_dedup import (
        average_hash,
        dedupe_images,
        dhash,
        hamming_distance,
        images_similar,
    )
    from je_auto_control.utils.url_canon import (
        build_query,
        canonicalize_url,
        normalize_url,
        parse_query,
        urls_equal,
    )
    from je_auto_control.utils.locale_parse import (
        format_currency,
        format_date,
        format_decimal,
        parse_decimal,
        parse_number,
    )
    from je_auto_control.utils.voice import (
        VoiceCommand,
        VoiceRouter,
        default_voice_router,
    )
    from je_auto_control.utils.coordinate_space import (
        CoordinateSpace,
        downscale_png,
        normalized_space,
        xga_space,
    )
    from je_auto_control.utils.loop_guard import (
        LoopGuard,
        LoopVerdict,
        default_loop_guard,
        digest_result,
    )
    from je_auto_control.utils.process_mining import (
        Candidate,
        MiningReport,
        SequencePattern,
        directly_follows,
        find_repeated_sequences,
        mine_action_log,
        rank_automation_candidates,
    )
    from je_auto_control.utils.assets import (
        Asset,
        AssetStore,
        AssetValue,
        active_environment,
    )
    from je_auto_control.utils.dotenv import (
        dotenv_values,
        dump_dotenv,
        load_dotenv,
        parse_dotenv,
    )
    from je_auto_control.utils.layered_config import (
        LayeredConfig,
        SourceTrace,
        deep_merge,
    )
    from je_auto_control.utils.config_schema import (
        ConfigField,
        ConfigSchema,
        coerce,
        validate_config,
    )
    from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
    from je_auto_control.utils.secret_ref import (
        RefResolver,
        SecretRefError,
        is_ref,
        resolve_ref,
        resolve_refs_in,
    )
    from je_auto_control.utils.config_redaction import (
        redact_config,
        redact_secret_text,
    )
    from je_auto_control.utils.events import (
        EventEmitter,
        post_cloudevent,
        to_cloudevent,
    )
    from je_auto_control.utils.notify_channels import (
        WebhookChannel,
        WebhookResult,
        notify_webhook,
        set_default_poster,
    )
    from je_auto_control.utils.jsonpath import (
        json_extract,
        json_query,
        json_query_one,
    )
    from je_auto_control.utils.saga import Saga, SagaResult, run_saga
    from je_auto_control.utils.decision_table import (
        DecisionTable,
        Rule,
        evaluate_table,
    )
    from je_auto_control.utils.locator_repair import (
        RepairStore,
        RepairSuggestion,
        repair_from_heal,
    )
    from je_auto_control.utils.pii_text import (
        PIIFinding,
        detect_pii,
        redact_pii_text,
    )
    from je_auto_control.utils.sarif import (
        from_audit_findings,
        from_lint_issues,
        make_finding,
        to_sarif,
        write_sarif,
    )
    from je_auto_control.utils.json_schema import (
        SchemaValidationResult,
        assert_schema,
        is_valid,
        validate_json,
    )
    from je_auto_control.utils.vuln_scan import (
        findings_to_sarif,
        is_affected,
        match_package,
        scan_components,
        version_key,
    )
    from je_auto_control.utils.vex import (
        VEX_JUSTIFICATIONS,
        VEX_STATUSES,
        apply_vex,
        build_vex,
        vex_statement,
    )
    from je_auto_control.utils.license_policy import (
        DEFAULT_COPYLEFT,
        evaluate_license,
        evaluate_sbom,
        license_findings_to_sarif,
        normalize_spdx,
    )
    from je_auto_control.utils.jwt import (
        ClaimsPolicy,
        ExpiredTokenError,
        InvalidSignatureError,
        JwtError,
        decode_jwt,
        encode_jwt,
    )
    from je_auto_control.utils.rate_limit import (
        SlidingWindowLimiter,
        TokenBucket,
        throttle,
    )
    from je_auto_control.utils.json_patch import (
        PatchError,
        PatchTestFailed,
        apply_patch,
        make_merge_patch,
        make_patch,
        merge_patch,
        remove_pointer,
        resolve_pointer,
        set_pointer,
    )
    from je_auto_control.utils.search_index import (
        SearchHit,
        SearchIndex,
        search_documents,
        tokenize,
    )
    from je_auto_control.utils.stats import (
        chi_square_2x2,
        cohens_d,
        describe,
        normal_cdf,
        percentile,
        two_proportion_z_test,
        welch_t_test,
    )
    from je_auto_control.utils.recurrence import (
        Recurrence,
        next_occurrence,
        occurrences,
        parse_rrule,
    )
    from je_auto_control.utils.text_diff import (
        MergeResult,
        PatchApplyError,
        apply_unified,
        three_way_merge,
        unified_diff,
    )
    from je_auto_control.utils.feature_flags import (
        Flag,
        FlagStore,
        assign_variant,
        evaluate_flag,
        is_enabled,
        percentage_bucket,
    )
    from je_auto_control.utils.provenance import (
        build_provenance,
        subject_for,
        subject_for_bytes,
        verify_provenance,
        write_provenance,
    )
    from je_auto_control.utils.json_contract import (
        MatchReport,
        diff_json,
        match_json,
        normalize_json,
        snapshot_json,
    )
    from je_auto_control.utils.chaos import (
        ChaosExperiment,
        Fault,
        Probe,
        exception_fault,
        latency_fault,
        run_experiment,
    )
    from je_auto_control.utils.slo import (
        BurnRule,
        burn_alerts,
        burn_rate,
        default_burn_rules,
        evaluate_slo,
    )
    from je_auto_control.utils.percentiles import LatencyDigest, exact_percentiles
    from je_auto_control.utils.timeseries import (
        ts_delta,
        ts_downsample,
        ts_idelta,
        ts_increase,
        ts_irate,
        ts_rate,
        ts_resample,
    )
    from je_auto_control.utils.anomaly import (
        detect_anomalies,
        ewma_control,
        mad_anomalies,
        mad_scores,
        zscore_anomalies,
        zscore_scores,
    )
    from je_auto_control.utils.smoothing import ewma, rolling, sma, wma
    from je_auto_control.utils.bulkhead import (
        Bulkhead,
        BulkheadFullError,
        next_delay,
        parse_ratelimit,
        parse_retry_after,
    )
    from je_auto_control.utils.http_cassette import Cassette, CassetteMissError
    from je_auto_control.utils.http_problem import (
        HttpProblemError,
        ProblemDetails,
        is_problem,
        parse_problem,
        raise_for_problem,
    )
    from je_auto_control.utils.sse_client import (
        SSEEvent,
        SSEParser,
        parse_event_stream,
    )
    from je_auto_control.utils.link_header import (
        Link,
        links_by_rel,
        next_url,
        paginate,
        parse_link_header,
    )
    from je_auto_control.utils.multipart import (
        MultipartFile,
        build_multipart,
        new_boundary,
        parse_multipart,
    )
    from je_auto_control.utils.http_content import (
        build_accept,
        build_accept_encoding,
        decode_body,
        negotiated_call,
        parse_quality_values,
    )
    from je_auto_control.utils.cookie_jar import CookieJar, parse_set_cookie
    from je_auto_control.utils.http_conditional import (
        conditioned_call,
        is_fresh,
        is_not_modified,
        parse_cache_control,
        store_validators,
    )
    from je_auto_control.utils.trace_context import (
        SpanContext,
        TraceContextError,
        child_context,
        extract_context,
        format_traceparent,
        format_tracestate,
        inject_context,
        new_root_context,
        new_span_id,
        new_trace_id,
        parse_traceparent,
        parse_tracestate,
    )
    from je_auto_control.utils.baggage import (
        Baggage,
        extract_baggage,
        format_baggage,
        inject_baggage,
        parse_baggage,
    )
    from je_auto_control.utils.canonical_log import (
        CanonicalLogLine,
        JSONLogFormatter,
        bind_trace_context,
    )
    from je_auto_control.utils.otlp_export import (
        attributes_to_otlp,
        spans_to_otlp,
        write_otlp,
    )
    from je_auto_control.utils.watchdog import (
        PopupWatchdog,
        WatchdogRule,
        default_popup_watchdog,
    )
    from je_auto_control.utils.ocr.ocr_engine import (
        TextMatch,
        click_text,
        find_text_matches,
        find_text_regex,
        locate_text_center,
        read_text_in_region,
        set_tesseract_cmd,
        wait_for_text,
    )
    from je_auto_control.utils.ocr.tesseract_setup import (
        OCRStatus,
        find_tesseract_cmd,
        ocr_languages,
        ocr_status,
        set_tessdata_dir,
    )
    from je_auto_control.utils.ocr.text_span import find_spans, group_lines
    from je_auto_control.utils.input_reach import (
        input_desktop_available,
        input_reaches_system,
    )
    from je_auto_control.utils.keyboard_layout import (
        char_table,
        foreground_keyboard_layout,
        layout_char_table,
        vk_to_char,
    )
    from je_auto_control.utils.llm import (
        LLMBackend,
        LLMNotAvailableError,
        LLMPlanError,
        plan_actions,
        run_from_description,
    )
    from je_auto_control.utils.agent.agent_loop import (
        AgentBackend,
        AgentBudget,
        AgentLoop,
        AgentResult,
        AgentStep,
        FakeAgentBackend,
        run_agent,
    )
    from je_auto_control.utils.agent.backends import (
        AgentBackendError,
        AnthropicAgentBackend,
        ComputerUseAgentBackend,
        OpenAIAgentBackend,
    )
    from je_auto_control.utils.agent.computer_use import (
        result_to_dict as computer_use_result_to_dict,
        run_computer_use,
    )
    from je_auto_control.utils.dag import (
        DagDefinition,
        DagDefinitionError,
        DagNode,
        DagRunResult,
        NodeResult,
        parse_dag,
        run_dag,
    )
    from je_auto_control.utils.remote_desktop.presence import (
        PresenceError,
        PresenceRegistry,
        ROLE_CONTROLLER,
        ROLE_OBSERVER,
        ViewerPresence,
        default_presence_registry,
    )
    from je_auto_control.utils.chatops import (
        ChatOpsError,
        CommandResult,
        CommandRouter,
        SlackBot,
        SlackError,
        make_default_slack_bot,
        register_chatops_default_commands,
    )
    from je_auto_control.utils.anchor_locator import (
        AnchorLocatorError,
        AnchorOutcome,
        Locator as AnchorLocator,
        a11y_locator,
        anchor_locate,
        anchor_locate_all,
        image_locator,
        ocr_locator,
        vlm_locator,
    )
    from je_auto_control.utils.ocr.structure import (
        OCRField,
        OCRRow,
        OCRTable,
        StructuredOCR,
        cluster_matches as ocr_cluster_matches,
        read_structure as ocr_read_structure,
    )
    from je_auto_control.utils.smart_waits import (
        WaitOutcome,
        wait_until_clipboard_changes,
        wait_until_color,
        wait_until_file,
        wait_until_gone,
        wait_until_image_gone,
        wait_until_pixel_changes,
        wait_until_port,
        wait_until_process,
        wait_until_region_idle,
        wait_until_screen_stable,
        wait_until_text_gone,
        wait_until_window_closed,
        wait_until_window_title,
    )
    from je_auto_control.utils.visual_regression import (
        DiffResult,
        MaskRegion,
        compare_to_golden,
        image_difference,
        take_golden,
    )
    from je_auto_control.utils.state_machine import (
        StateMachine,
        StateMachineError,
        run_state_machine,
    )
    from je_auto_control.utils.assertion import (
        AssertionResult,
        GroupAssertionResult,
        assert_all,
        assert_any,
        assert_by_description,
        assert_clipboard,
        assert_duration,
        assert_eventually,
        assert_file,
        assert_http,
        assert_image,
        assert_pixel,
        assert_process,
        assert_text,
        assert_variable,
        assert_window,
        run_assertion_spec,
    )
    from je_auto_control.utils.data_source import data_source_kinds, load_rows
    from je_auto_control.utils.flakiness import (
        FlakinessReport,
        FlakyEntry,
        analyze_flakiness,
    )
    from je_auto_control.utils.test_suite import (
        TestCaseResult,
        TestSuiteResult,
        run_suite,
        to_allure_results,
        to_junit_xml,
        write_allure_results,
        write_junit_xml,
    )
    from je_auto_control.utils.quarantine import (
        QuarantineEntry,
        QuarantineStore,
        auto_quarantine_from_flakiness,
        default_quarantine_store,
    )
    from je_auto_control.utils.a11y_audit import (
        AuditIssue,
        AuditReport,
        audit_contrast,
        audit_missing_labels,
        audit_target_size,
        contrast_ratio,
        detect_truncation,
        run_audit,
        wcag_audit,
    )
    from je_auto_control.utils.device_matrix import (
        DeviceResult,
        MatrixReport,
        run_on_devices,
    )
    from je_auto_control.utils.media_assert import (
        MediaAssertionResult,
        assert_audio_activity,
        assert_video_changes,
        measure_audio_rms,
        video_segment_motion,
    )
    from je_auto_control.utils.cost_telemetry import (
        CostEvent,
        CostSummary,
        default_cost_store,
        estimate_llm_usd,
        record_llm_call,
        summarise_llm_costs,
    )
    from je_auto_control.utils.failure_hooks import (
        FailureHookManager,
        FailureReport,
        GitHubBackend,
        JiraBackend,
        LinearBackend,
        TicketResult,
        default_failure_hook_manager,
    )
    from je_auto_control.utils.ab_locator import (
        ABRunOutcome,
        ab_best_strategy,
        ab_locate,
        ab_report_for,
        default_ab_store,
    )
    from je_auto_control.utils.remote_desktop import (
        AuthenticationError as RemoteDesktopAuthError,
        InputDispatchError as RemoteDesktopInputError,
        ProtocolError as RemoteDesktopProtocolError,
        RemoteDesktopHost,
        RemoteDesktopViewer,
    )
    from je_auto_control.utils.remote_desktop.connect_coordinator import (
        ConnectTarget as RemoteDesktopConnectTarget,
        UnresolvableTargetError as RemoteDesktopUnresolvableTargetError,
        parse_target as parse_remote_desktop_target,
    )
    from je_auto_control.utils.remote_desktop.registry import registry as remote_desktop_registry
    from je_auto_control.utils.gamepad import (
        GamepadUnavailable,
        VirtualGamepad,
        default_gamepad as default_virtual_gamepad,
        is_available as is_virtual_gamepad_available,
    )
    from je_auto_control.utils.mcp_server.disclosure import (
        ToolView,
        ToolPage,
        plan_mcp_tool_profile,
    )
    from je_auto_control.utils.mcp_server.discovery import (
        ToolDiscoveryError,
        ToolIndex,
        ToolSummary,
        search_mcp_tools,
        get_mcp_tool_schema,
    )
    from je_auto_control.utils.mcp_server import (
        AuditLogger,
        HttpMCPServer,
        MCPContent,
        MCPPrompt,
        MCPPromptArgument,
        MCPResource,
        MCPServer,
        MCPTool,
        MCPToolAnnotations,
        MCPToolResult,
        OperationCancelledError,
        PromptProvider,
        RateLimiter,
        ResourceProvider,
        ToolCallContext,
        build_default_tool_registry,
        default_prompt_provider,
        default_resource_provider,
        make_plugin_tool,
        register_plugin_tools,
        start_mcp_http_server,
        start_mcp_stdio_server,
    )
    from je_auto_control.utils.plugin_loader.plugin_loader import (
        discover_plugin_commands,
        load_plugin_directory,
        load_plugin_file,
        register_plugin_commands,
    )
    from je_auto_control.utils.rest_api.rest_server import (
        RestApiServer,
        start_rest_api_server,
    )
    from je_auto_control.utils.rbac import (
        AuthorizationContext,
        AuthorizationError,
        UserAuthError,
        UserRecord,
        UserStore,
        authorization_scope,
    )
    from je_auto_control.utils.admin import (
        AdminConsoleClient,
        AdminHost,
        default_admin_console,
    )
    from je_auto_control.utils.remote_desktop.webrtc_inspector import (
        WebRTCInspector,
        default_webrtc_inspector,
    )
    from je_auto_control.utils.usb import (
        UsbAcl,
        UsbDevice,
        UsbEnumerationResult,
        UsbEvent,
        UsbHotplugWatcher,
        UsbPassthroughClient,
        UsbPassthroughSession,
        default_usb_watcher,
        enable_usb_passthrough,
        is_usb_passthrough_enabled,
        list_usb_devices,
    )
    from je_auto_control.utils.exception.cancellation import (
        CancellationToken,
        TaskProgress,
        cancellation_scope,
    )
    from je_auto_control.wrapper.capabilities import (
        BackendContext,
        CapabilitySnapshot,
        CapabilityStatus,
        probe_capabilities,
    )
    from je_auto_control.utils.diagnostics import (
        Check,
        DiagnosticsReport,
        run_diagnostics,
    )
    from je_auto_control.utils.config_bundle import (
        ConfigBundleExporter,
        ConfigBundleImporter,
        ImportReport,
        export_config_bundle,
        import_config_bundle,
    )
    from je_auto_control.utils.profiler import (
        ActionProfiler,
        ActionStats,
        default_profiler,
    )
    from je_auto_control.utils.secrets import (
        SecretManager,
        SecretStoreError,
        SecretStoreLocked,
        default_secret_manager,
        default_secret_store_path,
    )
    from je_auto_control.utils.action_signing import (
        SigningConfig,
        VerifyResult,
        action_signing_config,
        create_signing_keypair,
        decrypt_action_file,
        encrypt_action_file,
        require_signed_actions,
        sign_action_file,
        verify_action_file,
    )
    from je_auto_control.utils.exception.exceptions import CryptographyUnavailableError
    from je_auto_control.utils.observability import (
        Counter as MetricCounter,
        Gauge as MetricGauge,
        Histogram as MetricHistogram,
        MetricRegistry,
        PrometheusExporter,
        Tracer,
        default_exporter as default_metrics_exporter,
        default_registry as default_metric_registry,
        default_tracer,
        render_metrics_text,
        traced,
    )
    from je_auto_control.utils.run_history.history_store import (
        HistoryStore,
        JournalLink,
        RunRecord,
        default_history_store,
    )
    from je_auto_control.utils.run_history import (
        HistoryBinding,
        manual_history_scope,
    )
    from je_auto_control.utils.action_journal import (
        ActionEvent,
        ActionJournal,
        ActionJournalError,
        JournalBinding,
        JournalRunOptions,
        JournalRunResult,
        execute_action_with_journal,
        execute_journal_run,
        inspect_journal,
        journal_scope,
        read_events,
    )
    from je_auto_control.utils.triggers.trigger_engine import (
        AllOfTrigger,
        AnyOfTrigger,
        CronTrigger,
        FilePathTrigger,
        ImageAppearsTrigger,
        PixelColorTrigger,
        SequenceTrigger,
        TriggerEngine,
        WindowAppearsTrigger,
        default_trigger_engine,
    )
    from je_auto_control.utils.triggers.webhook_server import (
        WebhookTrigger,
        WebhookTriggerServer,
        default_webhook_server,
    )
    from je_auto_control.utils.triggers.email_trigger import (
        EmailTrigger,
        EmailTriggerWatcher,
        default_email_trigger_watcher,
    )
    from je_auto_control.utils.recording_edit.editor import (
        adjust_delays,
        dedupe_moves,
        filter_actions,
        insert_action,
        merge_sleeps,
        remove_action,
        scale_coordinates,
        trim_actions,
    )
    from je_auto_control.utils.scheduler.scheduler import (
        ScheduledJob,
        Scheduler,
        default_scheduler,
    )
    from je_auto_control.utils.script_vars.execution import execution_scope
    from je_auto_control.utils.script_vars.interpolate import (
        interpolate_actions,
        interpolate_value,
        load_vars_from_json,
    )
    from je_auto_control.utils.script_vars.scope import VariableScope
    from je_auto_control.utils.watcher.watcher import (
        LogTail,
        MouseWatcher,
        PixelWatcher,
    )
    from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list
    from je_auto_control.utils.generate_report.generate_html_report import generate_html
    from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
    from je_auto_control.utils.generate_report.generate_json_report import generate_json
    from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
    from je_auto_control.utils.generate_report.generate_xml_report import generate_xml
    from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
    from je_auto_control.utils.json.json_file import (
        read_action_json,
        read_executable_action_json,
    )
    from je_auto_control.utils.json.json_file import write_action_json
    from je_auto_control.utils.json.json_file import format_action_json
    from je_auto_control.utils.codegen.codegen import (
        generate_code,
        generate_code_file,
    )
    from je_auto_control.utils.codegen.candidate_models import (
        CandidateGenerationError,
        CandidateScript,
    )
    from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
    from je_auto_control.utils.codegen.candidate_archive import write_candidate_archive
    from je_auto_control.utils.config_sync.client import (
        ConfigBucket,
        ConfigSyncClient,
        ConfigSyncError,
    )
    from je_auto_control.utils.config_sync.store import (
        ConfigRevisionConflict,
        ConfigStore,
        ConfigStoreError,
        ConfigStoreFull,
    )
    from je_auto_control.utils.config_sync.versions import (
        MergeDecision,
        SyncConflict,
        SyncEntry,
        merge_entries,
    )
    from je_auto_control.utils.config_sync.causal_models import (
        CausalConflict,
        DeletionFence,
        SyncActor,
    )
    from je_auto_control.utils.config_sync.causal_state import CausalBucket
    from je_auto_control.utils.config_sync.causal_store import CausalConfigStore
    from je_auto_control.utils.config_sync.causal_client import CausalSyncClient
    from je_auto_control.utils.config_sync.causal_receipt import CausalReceipt
    from je_auto_control.utils.config_sync.control_models import (
        SyncControlOperation,
        SyncControlRequest,
        SyncControlResult,
    )
    from je_auto_control.utils.config_sync.asset_models import (
        AssetFile,
        AssetManifest,
        AssetSyncResult,
    )
    from je_auto_control.utils.config_sync.adapter_references import (
        SyncBindings,
        SyncReference,
    )
    from je_auto_control.utils.config_sync.adapter_schema import ApplyReport
    from je_auto_control.utils.config_sync.adapter_state import SyncAdapterState
    from je_auto_control.utils.config_sync.adapters import (
        AddressBookSyncAdapter,
        HotkeySyncAdapter,
        LocatorSyncAdapter,
        ScriptSyncAdapter,
        SettingsSyncAdapter,
        SyncAdapter,
        TriggerSyncAdapter,
        WorkspaceSettingsSyncAdapter,
    )
    from je_auto_control.utils.config_sync.adapter_profiles import materialize_sync_profile
    from je_auto_control.utils.config_sync.adapter_factory import adapter_from_profile
    from je_auto_control.utils.config_sync.workspace_sync import SyncWorkspace
    from je_auto_control.utils.config_sync.profile_load import load_sync_profile
    from je_auto_control.utils.config_sync.profile_models import LoadedSyncProfile
    from je_auto_control.utils.config_sync.blob_models import (
        SyncAssetBlob,
        SyncAssetReference,
    )
    from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
    from je_auto_control.utils.config_sync.blob_http import SyncAssetHTTPClient
    from je_auto_control.utils.config_sync.workspace_models import (
        SyncWorkspaceError,
        WorkspaceSyncResult,
    )
    from je_auto_control.utils.config_sync.assets import (
        AssetTransport,
        DirectoryAssetTransport,
        build_asset_manifest,
        sync_assets,
    )
    from je_auto_control.utils.config_sync.peers import (
        FullResyncRequired,
        SyncPeer,
        SyncPeers,
    )
    from je_auto_control.utils.config_sync.outbox import (
        SyncDrainResult,
        SyncLocalIdentity,
        SyncOperation,
        SyncOutbox,
        SyncRetryPolicy,
    )
    from je_auto_control.utils.http_client.http_client import http_request
    from je_auto_control.utils.sql.sql_query import query_sqlite
    from je_auto_control.utils.email_send.email_sender import send_email
    from je_auto_control.utils.pdf.pdf_reader import (
        assert_pdf_text,
        extract_pdf_text,
        pdf_metadata,
        pdf_page_count,
    )
    from je_auto_control.utils.package_manager.package_manager_class import package_manager
    from je_auto_control.utils.project.create_project_structure import create_project_dir
    from je_auto_control.utils.shell_process.shell_exec import ShellManager
    from je_auto_control.utils.shell_process.shell_exec import default_shell_manager
    from je_auto_control.utils.socket_server.auto_control_socket_server import (
        start_autocontrol_socket_server,
    )
    from je_auto_control.utils.start_exe.start_another_process import start_exe
    from je_auto_control.utils.test_record.record_test_class import test_record_instance
    from je_auto_control.wrapper.auto_control_image import locate_all_image
    from je_auto_control.wrapper.auto_control_image import locate_and_click
    from je_auto_control.wrapper.auto_control_image import locate_image_center
    from je_auto_control.wrapper.auto_control_keyboard import check_key_is_press
    from je_auto_control.wrapper.auto_control_keyboard import get_keyboard_keys_table
    from je_auto_control.wrapper.auto_control_keyboard import hotkey
    from je_auto_control.wrapper.auto_control_keyboard import keyboard_key_name
    from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key
    from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key
    from je_auto_control.wrapper.auto_control_keyboard import send_key_event_to_window
    from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
    from je_auto_control.wrapper.auto_control_keyboard import write
    from je_auto_control.wrapper.auto_control_keyboard import write_secret
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
    from je_auto_control.utils.humanize.motion import (
        HumanizedMotion,
        humanized_path,
        move_mouse_humanized,
    )
    from je_auto_control.utils.humanize.typing import (
        humanized_key_delays,
        type_text_humanized,
    )
    from je_auto_control.wrapper.auto_control_record import record
    from je_auto_control.wrapper.auto_control_record import stop_record
    from je_auto_control.wrapper.auto_control_record import stop_record_timeline
    from je_auto_control.wrapper.auto_control_record import record_to_json
    from je_auto_control.wrapper.auto_control_screen import screen_size
    from je_auto_control.wrapper.auto_control_screen import screenshot
    from je_auto_control.wrapper.auto_control_screen import get_pixel
    from je_auto_control.wrapper.auto_control_window import (
        close_window_by_title,
        find_window,
        focus_window,
        foreground_window,
        foreground_window_process_id,
        list_windows,
        minimize_window_by_title,
        minimize_windows_for_process,
        move_window_by_title,
        post_click_to_window,
        post_key_to_window,
        show_window_by_title,
        wait_for_window,
        window_process_id,
        window_rect,
        windows_for_process_id,
    )

if _sys.platform in ("win32", "cygwin", "msys"):
    if _TYPE_CHECKING:
        from je_auto_control.windows.window import windows_window_manage
else:
    windows_window_manage = None  # type: ignore[assignment]


def start_autocontrol_gui(*args, **kwargs):
    """Launch the GUI (imports PySide6 lazily so headless usage stays Qt-free)."""
    from je_auto_control.gui import start_autocontrol_gui as _impl
    return _impl(*args, **kwargs)

__all__ = [
    "AgentTargetProfile", "manage_agent_target", "list_agent_targets",
    "draft_agent_workflow", "workflow_download", "workflow_manifest", "workflow_control", "workflow_open",
    "workflow_wait", "browser_navigate", "browser_click", "browser_fill", "browser_select", "browser_check",
    "browser_read", "browser_wait", "browser_link", "browser_download", "browser_upload",
    "AgentActionRequest", "AgentActionResult", "AgentControlBusy", "AgentObservation", "AgentRuntime",
    "AgentTaskBudget", "AgentTaskError", "AgentTaskHandle", "AgentTaskResult", "AgentTaskSpec",
    "get_agent_task_receipts", "reconcile_agent_task", "prune_agent_tasks",
    "recover_agent_target",
    "AgentObservationStale",
    "AgentHumanReview",
    "manage_agent_transfer", "manage_agent_skill", "list_agent_skills", "manage_agent_recovery",
    "manage_agent_trigger", "list_agent_triggers",
    "act_agent_task", "agent_runtime_status", "cancel_agent_task", "finish_agent_task", "get_agent_task",
    "lookup_agent_task",
    "inspect_agent_dag", "manage_agent_dag",
    "list_agent_tasks", "observe_agent_task", "pause_agent_task", "resume_agent_task", "start_agent_runtime",
    "submit_agent_task",
    "stop_agent_runtime", "stop_all_agent_tasks",
    "SyncWorkspace", "SyncWorkspaceError", "WorkspaceSyncResult",
    "load_sync_profile", "LoadedSyncProfile",
    "SyncAssetBlob", "SyncAssetReference", "SyncAssetStore",
    "SyncAssetHTTPClient",
    "SyncControlOperation", "SyncControlRequest", "SyncControlResult",
    "AssetFile", "AssetManifest", "AssetSyncResult", "AssetTransport", "DirectoryAssetTransport",
    "SyncBindings", "SyncReference", "ApplyReport", "SyncAdapterState", "SyncAdapter", "ScriptSyncAdapter",
    "LocatorSyncAdapter", "HotkeySyncAdapter", "TriggerSyncAdapter", "AddressBookSyncAdapter", "SettingsSyncAdapter",
    "WorkspaceSettingsSyncAdapter",
    "materialize_sync_profile",
    "adapter_from_profile",
    "build_asset_manifest", "sync_assets",
    "CausalSyncClient", "CausalReceipt",
    "CausalBucket", "CausalConfigStore", "CausalConflict", "DeletionFence", "SyncActor",
    "MergeDecision", "SyncConflict", "SyncEntry", "merge_entries", "FullResyncRequired", "SyncPeer", "SyncPeers",
    "SyncDrainResult", "SyncLocalIdentity", "SyncOperation", "SyncOutbox", "SyncRetryPolicy",
    "ConfigBucket", "ConfigSyncClient", "ConfigSyncError", "ConfigStore",
    "ConfigRevisionConflict", "ConfigStoreError", "ConfigStoreFull",
    "click_mouse", "mouse_keys_table", "get_mouse_position", "press_mouse", "release_mouse",
    "mouse_scroll", "mouse_scroll_error_message", "set_mouse_position", "special_mouse_keys_table",
    "HumanizedMotion", "humanized_path", "move_mouse_humanized",
    "humanized_key_delays", "type_text_humanized",
    "keyboard_keys_table", "press_keyboard_key", "release_keyboard_key", "type_keyboard", "check_key_is_press",
    "write", "write_secret", "hotkey", "start_exe", "get_keyboard_keys_table", "keyboard_key_name",
    "screen_size", "screenshot", "locate_all_image", "locate_image_center", "locate_and_click",
    "CriticalExit", "AutoControlException", "AutoControlKeyboardException",
    "AutoControlMouseException", "AutoControlCantFindKeyException",
    "AutoControlScreenException", "AutoControlFlatTemplateException",
    "ImageNotFoundException", "AutoControlJsonActionException",
    "AutoControlRecordException", "AutoControlActionNullException", "AutoControlActionException", "record",
    "stop_record", "stop_record_timeline",
    "read_action_json", "read_executable_action_json", "write_action_json", "format_action_json",
    "execute_action", "execute_files", "executor",
    "execute_action_with_vars", "record_to_json",
    "generate_code", "generate_code_file", "generate_candidate_from_log", "CandidateGenerationError", "CandidateScript",
    "write_candidate_archive", "http_request", "query_sqlite",
    "send_email", "assert_pdf_text", "extract_pdf_text", "pdf_metadata",
    "pdf_page_count",
    "add_command_to_executor", "test_record_instance", "pil_screenshot",
    # OCR
    "TextMatch", "find_text_matches", "locate_text_center", "wait_for_text",
    "click_text", "set_tesseract_cmd", "read_text_in_region",
    "find_text_regex", "find_spans", "group_lines",
    "OCRStatus", "find_tesseract_cmd", "ocr_languages", "ocr_status",
    "set_tessdata_dir",
    "char_table", "foreground_keyboard_layout", "layout_char_table",
    "vk_to_char", "input_desktop_available", "input_reaches_system",
    # Recording editor
    "trim_actions", "insert_action", "remove_action", "filter_actions",
    "adjust_delays", "scale_coordinates", "dedupe_moves", "merge_sleeps",
    # Scheduler
    "Scheduler", "ScheduledJob", "default_scheduler",
    # Script variables
    "interpolate_actions", "interpolate_value", "load_vars_from_json",
    "VariableScope", "execution_scope",
    # Watchers
    "MouseWatcher", "PixelWatcher", "LogTail",
    # Window manager
    "list_windows", "find_window", "focus_window", "wait_for_window",
    "close_window_by_title", "show_window_by_title",
    "minimize_window_by_title", "foreground_window", "window_rect",
    "move_window_by_title", "foreground_window_process_id",
    "window_process_id", "post_key_to_window", "post_click_to_window",
    "windows_for_process_id", "minimize_windows_for_process",
    # Clipboard
    "get_clipboard", "set_clipboard",
    "get_clipboard_image", "set_clipboard_image",
    # Hotkey daemon
    "HotkeyDaemon", "HotkeyBinding", "default_hotkey_daemon",
    "PopupWatchdog", "WatchdogRule", "default_popup_watchdog",
    "generate_totp", "verify_totp", "generate_secret", "TOTPError",
    "handle_file_dialog", "FileDialogDriver",
    "ensure_interactive_session", "is_session_locked",
    "WorkQueue", "WorkItem", "BusinessError", "WorkQueueError",
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
    "infer_schema", "profile_rows",
    "categorical_drift", "detect_drift", "ks_two_sample", "psi",
    "SchemaChange", "check_compatibility", "diff_schemas",
    "is_backward_compatible", "is_forward_compatible", "is_full_compatible",
    "cell_changes", "diff_rows", "summarize_diff",
    "check_accepted_values", "check_foreign_key", "check_row_count",
    "check_unique_key",
    "check_catalog", "check_overflow", "pseudo_localize",
    "pseudo_localize_catalog",
    "Checkpoint", "CheckpointStore", "CheckpointStoreError", "run_resumable",
    "mark_click", "mark_elements", "mark_screen", "render_marks",
    "resolve_mark",
    "describe_screen", "diff_snapshots", "screen_changed", "snapshot",
    "snapshot_screen",
    "replay_timeline", "run_sequence",
    "CircuitBreaker", "CircuitOpenError", "RetryPolicy", "retry_call",
    "IdempotencyConflict", "IdempotencyStore", "request_fingerprint",
    "DedupWindow", "SequenceTracker",
    "VersionConflict", "VersionedStore", "check_if_match", "if_match_header",
    "Outbox",
    "collation_key",
    "collation_compare",
    "sort_strings",
    "confusable_skeleton",
    "detect_homoglyphs",
    "is_confusable",
    "is_mixed_script",
    "scripts_of",
    "automated_readability_index",
    "count_syllables",
    "flesch_kincaid_grade",
    "flesch_reading_ease",
    "gunning_fog",
    "readability_report",
    "readability_stats",
    "smog_index",
    "base_direction",
    "bidi_controls",
    "detect_bidi_issues",
    "has_bidi_controls",
    "is_bidi_balanced",
    "is_trojan_source",
    "strip_bidi_controls",
    "format_list",
    "format_message",
    "ordinal_category",
    "plural_category",
    "GettextCatalog",
    "parse_po",
    "parse_po_file",
    "read_mo",
    "read_mo_file",
    "luhn_validate",
    "luhn_check_digit",
    "verhoeff_validate",
    "verhoeff_check_digit",
    "damm_validate",
    "damm_check_digit",
    "mod97_10_validate",
    "mod97_10_check_digits",
    "plan_path",
    "move_along_path",
    "drag_path",
    "path_easings",
    "plan_field_set",
    "set_field_text",
    "plan_key_hold",
    "hold_key",
    "move_mouse_relative",
    "relative_target",
    "type_unicode",
    "type_unicode_keys",
    "type_unicode_text",
    "plan_paste",
    "plan_unicode_keys",
    "unicode_code_units",
    "unicode_keys_supported",
    "hold_modifiers",
    "plan_with_modifiers",
    "cluster_grid",
    "locate_cell",
    "TemplateMatch",
    "match_template",
    "match_template_all",
    "match_masked",
    "match_masked_all",
    "best_matches",
    "RotatedMatch",
    "match_rotated",
    "match_rotated_all",
    "scale_space",
    "TrustedMatch",
    "match_with_trust",
    "score_peaks",
    "auto_threshold",
    "match_auto",
    "edge_match",
    "edge_match_all",
    "chamfer_distance",
    "match_ensemble",
    "vote_centers",
    "match_color",
    "match_color_all",
    "region_stability",
    "match_persistence",
    "SubPixelMatch",
    "match_subpixel",
    "refine_peak",
    "GridCell",
    "grid_cells",
    "cell_for_point",
    "point_for_cell",
    "assign_text_to_grid",
    "populate_table",
    "table_to_records",
    "table_to_csv",
    "delta_index",
    "delta_observation",
    "summarize_delta",
    "vertical_projection",
    "column_gutters",
    "assign_columns",
    "detect_borderless_table",
    "xy_cut",
    "flow_order",
    "to_blocks",
    "group_paragraphs",
    "detect_lists",
    "classify_lines",
    "outline",
    "associate_fields",
    "match_labels_to_widgets",
    "checkbox_state",
    "EffectVerdict",
    "classify_effect",
    "effect_near_point",
    "is_no_op",
    "PostconditionReport",
    "check_postcondition",
    "compile_postcondition",
    "RepairPolicy",
    "RepairOutcome",
    "plan_repair",
    "next_tactic",
    "run_with_repair",
    "ConsensusResult",
    "consensus_point",
    "consensus_element",
    "is_confident",
    "SettleState",
    "SettleTracker",
    "settle_point",
    "is_settled",
    "build_critic_record",
    "score_step_rule_based",
    "to_judge_prompt",
    "find_color_region",
    "find_color_regions",
    "ssim_compare",
    "ssim_changed_regions",
    "feature_match",
    "FeatureMatch",
    "find_shapes",
    "find_rectangles",
    "WindowRect",
    "available_slots",
    "tile_rect",
    "grid_rects",
    "cascade_rects",
    "preprocess_image",
    "to_grayscale",
    "binarize",
    "upscale",
    "denoise",
    "deskew",
    "detect_skew_angle",
    "enhance_contrast",
    "Monitor",
    "enumerate_monitors",
    "monitor_at_point",
    "monitor_for_window",
    "primary_monitor",
    "remap_point",
    "to_local",
    "to_virtual",
    "virtual_bounds",
    "grab_logical",
    "logical_virtual_rect",
    "logical_scale",
    "needs_rescale",
    "wait_actionable",
    "act_when_ready",
    "ActionabilityReport",
    "GateConfig",
    "iou",
    "merge_boxes",
    "fuse_elements",
    "reading_order",
    "segment_hsv",
    "color_mask",
    "dominant_hue_regions",
    "find_text_regions",
    "find_text_lines",
    "find_lines",
    "find_grid",
    "find_separators",
    "expect_poll",
    "assert_poll",
    "PollResult",
    "to_equal",
    "to_contain",
    "to_be_greater_than",
    "to_match_regex",
    "to_be_truthy",
    "to_be_stable",
    "Candidates",
    "from_boxes",
    "build_cf_html",
    "parse_cf_html",
    "get_clipboard_html",
    "set_clipboard_html",
    "build_dropfiles",
    "parse_dropfiles",
    "set_clipboard_files",
    "get_clipboard_files",
    "image_histogram",
    "compare_histograms",
    "histogram_changed",
    "changed_regions",
    "has_motion",
    "activity_score",
    "plan_zorder",
    "set_topmost",
    "bring_to_front",
    "send_to_back",
    "SoftAssertions", "SoftAssertionsFailed",
    "perceptual_diff",
    "assert_perceptual",
    "PerceptualDiffResult",
    "frame_insets",
    "client_to_screen",
    "get_client_rect",
    "client_point",
    "canonical_action",
    "from_anthropic",
    "from_openai_cua",
    "to_ac_command",
    "flatten_tree",
    "observation_index",
    "serialize_observation",
    "in_bounds",
    "snap_to_element",
    "validate_action",
    "record_step",
    "to_jsonl",
    "from_jsonl",
    "replay_trace",
    "match_elements",
    "assign_stable_ids",
    "score_candidates",
    "best_candidate",
    "ScoredCandidate",
    "read_barcodes",
    "emit_annotations", "format_annotation",
    "ClipboardHistory", "default_clipboard_history",
    "analyze_heal_log", "heal_stats", "scan_secrets",
    "describe_step", "generate_sop", "write_sop",
    "easing_names", "tween_drag", "tween_points",
    "COMMANDS_GROUP", "discover_plugins", "load_plugins",
    "ApprovalGate", "CredentialBroker", "CredentialBrokerError", "approval_gate",
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
    "deaccent", "fold_whitespace", "normalize_quotes", "normalize_text",
    "slugify",
    "damerau_levenshtein", "dice", "jaccard", "jaro", "jaro_winkler",
    "levenshtein", "similarity",
    "minhash_signature", "minhash_similarity", "near_duplicates", "simhash",
    "S3ArtifactStore", "configure_default_store", "get_default_store",
    "set_default_store",
    "average_hash", "dedupe_images", "dhash", "hamming_distance",
    "images_similar",
    "build_query", "canonicalize_url", "normalize_url", "parse_query",
    "urls_equal",
    "format_currency", "format_date", "format_decimal", "parse_decimal",
    "parse_number",
    "VoiceCommand", "VoiceRouter", "default_voice_router",
    "CoordinateSpace", "downscale_png", "normalized_space", "xga_space",
    "LoopGuard", "LoopVerdict", "default_loop_guard", "digest_result",
    "Candidate", "MiningReport", "SequencePattern", "directly_follows",
    "find_repeated_sequences", "mine_action_log",
    "rank_automation_candidates",
    "Asset", "AssetStore", "AssetValue", "active_environment",
    "dotenv_values", "dump_dotenv", "load_dotenv", "parse_dotenv",
    "LayeredConfig", "SourceTrace", "deep_merge",
    "ConfigField", "ConfigSchema", "coerce", "validate_config",
    "PathNotAllowedError", "PathPolicy",
    "RefResolver", "SecretRefError", "is_ref", "resolve_ref", "resolve_refs_in",
    "redact_config", "redact_secret_text",
    "EventEmitter", "post_cloudevent", "to_cloudevent",
    "WebhookChannel", "WebhookResult", "notify_webhook", "set_default_poster",
    "json_extract", "json_query", "json_query_one",
    "Saga", "SagaResult", "run_saga",
    "DecisionTable", "Rule", "evaluate_table",
    "RepairStore", "RepairSuggestion", "repair_from_heal",
    "PIIFinding", "detect_pii", "redact_pii_text",
    "from_audit_findings", "from_lint_issues", "make_finding", "to_sarif",
    "write_sarif",
    "SchemaValidationResult", "assert_schema", "is_valid", "validate_json",
    "findings_to_sarif", "is_affected", "match_package", "scan_components",
    "version_key",
    "VEX_JUSTIFICATIONS", "VEX_STATUSES", "apply_vex", "build_vex",
    "vex_statement",
    "DEFAULT_COPYLEFT", "evaluate_license", "evaluate_sbom",
    "license_findings_to_sarif", "normalize_spdx",
    "ClaimsPolicy", "ExpiredTokenError", "InvalidSignatureError", "JwtError",
    "decode_jwt", "encode_jwt",
    "SlidingWindowLimiter", "TokenBucket", "throttle",
    "PatchError", "PatchTestFailed", "apply_patch", "make_merge_patch",
    "make_patch", "merge_patch", "remove_pointer", "resolve_pointer",
    "set_pointer",
    "SearchHit", "SearchIndex", "search_documents", "tokenize",
    "chi_square_2x2", "cohens_d", "describe", "normal_cdf", "percentile",
    "two_proportion_z_test", "welch_t_test",
    "Recurrence", "next_occurrence", "occurrences", "parse_rrule",
    "MergeResult", "PatchApplyError", "apply_unified", "three_way_merge",
    "unified_diff",
    "Flag", "FlagStore", "assign_variant", "evaluate_flag", "is_enabled",
    "percentage_bucket",
    "build_provenance", "subject_for", "subject_for_bytes",
    "verify_provenance", "write_provenance",
    "MatchReport", "diff_json", "match_json", "normalize_json", "snapshot_json",
    "ChaosExperiment", "Fault", "Probe", "exception_fault", "latency_fault",
    "run_experiment",
    "BurnRule", "burn_alerts", "burn_rate", "default_burn_rules", "evaluate_slo",
    "LatencyDigest", "exact_percentiles",
    "ts_delta", "ts_downsample", "ts_idelta", "ts_increase", "ts_irate",
    "ts_rate", "ts_resample",
    "detect_anomalies", "ewma_control", "mad_anomalies", "mad_scores",
    "zscore_anomalies", "zscore_scores",
    "ewma", "rolling", "sma", "wma",
    "Bulkhead", "BulkheadFullError", "next_delay", "parse_ratelimit",
    "parse_retry_after",
    "Cassette", "CassetteMissError",
    "HttpProblemError", "ProblemDetails", "is_problem", "parse_problem",
    "raise_for_problem",
    "SSEEvent", "SSEParser", "parse_event_stream",
    "Link", "links_by_rel", "next_url", "paginate", "parse_link_header",
    "MultipartFile", "build_multipart", "new_boundary", "parse_multipart",
    "build_accept", "build_accept_encoding", "decode_body", "negotiated_call",
    "parse_quality_values",
    "CookieJar", "parse_set_cookie",
    "conditioned_call", "is_fresh", "is_not_modified", "parse_cache_control",
    "store_validators",
    "SpanContext", "TraceContextError", "child_context", "extract_context",
    "format_traceparent", "format_tracestate", "inject_context",
    "new_root_context", "new_span_id", "new_trace_id", "parse_traceparent",
    "parse_tracestate",
    "Baggage", "extract_baggage", "format_baggage", "inject_baggage",
    "parse_baggage",
    "CanonicalLogLine", "JSONLogFormatter", "bind_trace_context",
    "attributes_to_otlp", "spans_to_otlp", "write_otlp",
    # MCP server
    "ToolView", "ToolPage", "plan_mcp_tool_profile",
    "ToolDiscoveryError", "ToolIndex", "ToolSummary", "search_mcp_tools", "get_mcp_tool_schema",
    "AuditLogger", "HttpMCPServer", "MCPContent", "MCPPrompt",
    "MCPPromptArgument", "MCPResource", "MCPServer", "MCPTool",
    "MCPToolAnnotations", "MCPToolResult", "OperationCancelledError", "PromptProvider",
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
    # RBAC
    "AuthorizationContext", "AuthorizationError", "UserAuthError",
    "UserRecord", "UserStore", "authorization_scope",
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
    "BackendContext", "CapabilitySnapshot", "CapabilityStatus", "probe_capabilities",
    "CancellationToken", "TaskProgress", "cancellation_scope",
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
    "SigningConfig", "action_signing_config", "create_signing_keypair",
    "CryptographyUnavailableError",
    "require_signed_actions", "encrypt_action_file", "decrypt_action_file",
    # Observability (Prometheus + OpenTelemetry)
    "MetricCounter", "MetricGauge", "MetricHistogram",
    "MetricRegistry", "default_metric_registry",
    "PrometheusExporter", "default_metrics_exporter", "render_metrics_text",
    "Tracer", "default_tracer", "traced",
    # Run history
    "HistoryStore", "JournalLink", "RunRecord", "default_history_store",
    "HistoryBinding", "manual_history_scope",
    "ActionEvent", "ActionJournal", "ActionJournalError", "JournalBinding", "JournalRunOptions", "JournalRunResult",
    "execute_action_with_journal", "execute_journal_run", "inspect_journal", "journal_scope", "read_events",
    # Accessibility
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "accessibility_status",
    "AccessibilityRecorder", "AXRecorderEvent", "AXTreeNode",
    "click_accessibility_element", "dump_accessibility_tree",
    "find_accessibility_element", "find_accessibility_elements",
    "focused_accessibility_element", "list_accessibility_elements",
    "control_get_state", "control_get_value", "control_set_value",
    "control_invoke", "control_toggle", "read_control_table",
    "expand_control", "collapse_control", "control_expand_state",
    "select_control_item", "control_range", "set_control_range",
    "scroll_control_into_view",
    "get_control_text", "get_selected_text", "get_visible_text",
    "find_control_text", "select_control_text", "control_text_attributes",
    "control_type_name", "humanize_role", "humanize_tree",
    "assign_node_paths", "find_by_path",
    "is_interactive_role", "tab_order", "audit_focus_order", "focus_control",
    "realize_item",
    "get_element_properties", "is_element_enabled",
    "table_headers", "table_cell", "cell_by_header",
    "move_element", "resize_element", "set_window_state",
    "window_interaction_state",
    "legacy_info", "legacy_default_action",
    "get_selection", "list_views", "set_view",
    "wait_for_focus_change",
    "plan_open", "open_path",
    "idle_seconds", "is_idle", "plan_keep_awake",
    "keep_awake", "keep_awake_on", "allow_sleep",
    "normalize_ext", "file_association",
    "get_volume", "set_volume", "change_volume",
    "is_muted", "set_mute", "mute", "unmute", "toggle_mute",
    "lock_session", "plan_lock_session", "wait_for_unlock",
    "wait_for_lock", "classify_lock_transitions",
    "ime_state", "is_composing", "wait_for_composition_commit",
    "decode_conversion_mode",
    "RetryBudget", "run_with_budget", "backoff_delay", "jittered_delay",
    "compare_field_value", "verify_field_value", "fill_and_verify",
    "recommend_timeout", "timeout_stats",
    "ensure_state", "ensure_toggle",
    "wait_until_app_idle", "idle_point",
    "simulate_cvd", "colors_collide", "color_distance",
    "place_labels", "label_color",
    "grade_contrast", "dominant_pair", "region_contrast",
    "normalize_theme", "match_theme",
    "localize_changes", "rank_changes",
    "classify_widget", "box_features", "classify_icon",
    "propose_elements", "tag_kinds",
    "act_in_view", "ScrollPlan", "act_with_mode",
    "build_rtf", "rtf_to_text", "rows_to_csv", "csv_to_rows",
    "set_clipboard_rtf", "get_clipboard_rtf",
    "set_clipboard_csv", "get_clipboard_csv",
    "classify_format", "classify_formats", "diff_formats",
    "list_clipboard_formats", "clipboard_formats",
    "plan_file_drop", "drop_files",
    "image_quality", "is_blurry", "quality_gate",
    "detect_scale", "scale_sweep",
    "saliency_map", "salient_regions", "most_salient",
    "normalize_error", "failure_signature", "group_failures",
    "diff_runs", "summarize_run_diff",
    "cofailure_pairs", "failure_clusters",
    "build_timeline", "critical_steps",
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
    "a11y_locator", "anchor_locate", "anchor_locate_all", "image_locator",
    "ocr_locator",
    "vlm_locator",
    # Structured OCR
    "OCRField", "OCRRow", "OCRTable", "StructuredOCR",
    "ocr_cluster_matches", "ocr_read_structure",
    # Smart waits
    "WaitOutcome", "wait_until_pixel_changes",
    "wait_until_region_idle", "wait_until_screen_stable",
    "wait_until_clipboard_changes", "wait_until_window_closed",
    "wait_until_file", "wait_until_port", "wait_until_process",
    "wait_until_gone", "wait_until_image_gone", "wait_until_text_gone",
    "wait_until_color", "wait_until_window_title",
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
    "SelfHealRequest", "SelfHealRequestError", "SelfHealRunResult", "SelfHealVerificationError",
    "VerificationRequest", "self_heal_run", "inspect_heal_source",
    "create_template_candidate", "preview_template_candidate", "verify_template_candidate",
    "accept_template_candidate", "revert_template_candidate", "TemplateCandidateState", "TemplateCandidatePreview",
    "TemplateCandidateVerification", "TemplateCandidateTransition", "TemplateRevisionError", "TemplateRevisionConflict",
    "EvaluationRatio", "EvaluationSample", "HealingAttempt", "HealingComparison", "HealingEvaluationError",
    "HealingVersionReport", "LocatorCandidate", "LocatorStrategy", "TemplateFrameLocator", "VLMFrameLocator",
    "evaluate_healing_manifest", "evaluate_locators", "write_healing_report",
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
    "arrange_grid", "arrange_cascade",
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


keyboard_keys_table: dict[str, int]


def __getattr__(name: str) -> object:
    """Resolve one export, keeping the mutable platform key table uncached."""
    if name == "keyboard_keys_table":
        return getattr(_sys.modules[__name__], "get_keyboard_keys_table")()
    return _resolve_export(globals(), _EXPORTS, name)


def __dir__() -> list[str]:
    """List public exports without importing their owners."""
    return sorted(set(globals()) | set(__all__))
