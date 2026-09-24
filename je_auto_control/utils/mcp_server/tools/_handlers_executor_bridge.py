"""MCP adapters that delegate straight to the executor's own implementation.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
from typing import Any, Dict, List, Optional


def expand_control(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _expand_control
    return _expand_control(name, role, app_name, automation_id)


def collapse_control(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _collapse_control
    return _collapse_control(name, role, app_name, automation_id)


def control_expand_state(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _control_expand_state
    return _control_expand_state(name, role, app_name, automation_id)


def select_control_item(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _select_control_item
    return _select_control_item(name, role, app_name, automation_id)


def control_range(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _control_range
    return _control_range(name, role, app_name, automation_id)


def set_control_range(value, name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.executor.action_executor import _set_control_range
    return _set_control_range(value, name, role, app_name, automation_id)


def scroll_control_into_view(name=None, role=None, app_name=None,
                             automation_id=None):
    from je_auto_control.utils.executor.action_executor import _scroll_control_into_view
    return _scroll_control_into_view(name, role, app_name, automation_id)


def get_control_text(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_control_text
    return _get_control_text(name, role, app_name, automation_id)


def find_control_text(text, ignore_case=True, name=None, role=None,
                      app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _find_control_text
    return _find_control_text(text, ignore_case, name, role, app_name,
                              automation_id)


def select_control_text(text, ignore_case=True, name=None, role=None,
                        app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _select_control_text
    return _select_control_text(text, ignore_case, name, role, app_name,
                                automation_id)


def control_text_attributes(name=None, role=None, app_name=None,
                            automation_id=None):
    from je_auto_control.utils.executor.action_executor import _control_text_attributes
    return _control_text_attributes(name, role, app_name, automation_id)


def realize_item(item_name, by="name", container_name=None, container_role=None,
                 app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _realize_item
    return _realize_item(item_name, by, container_name, container_role,
                         app_name, automation_id)


def get_element_properties(name=None, role=None, app_name=None,
                           automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_element_properties
    return _get_element_properties(name, role, app_name, automation_id)


def table_headers(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _table_headers
    return _table_headers(name, role, app_name, automation_id)


def table_cell(row, column, name=None, role=None, app_name=None,
               automation_id=None):
    from je_auto_control.utils.executor.action_executor import _table_cell
    return _table_cell(row, column, name, role, app_name, automation_id)


def cell_by_header(row, column_header, name=None, role=None, app_name=None,
                   automation_id=None):
    from je_auto_control.utils.executor.action_executor import _cell_by_header
    return _cell_by_header(row, column_header, name, role, app_name,
                           automation_id)


def move_element(x, y, name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _move_element
    return _move_element(x, y, name, role, app_name, automation_id)


def resize_element(width, height, name=None, role=None, app_name=None,
                   automation_id=None):
    from je_auto_control.utils.executor.action_executor import _resize_element
    return _resize_element(width, height, name, role, app_name, automation_id)


def set_window_state(state, name=None, role=None, app_name=None,
                     automation_id=None):
    from je_auto_control.utils.executor.action_executor import _set_window_state
    return _set_window_state(state, name, role, app_name, automation_id)


def window_interaction_state(name=None, role=None, app_name=None,
                             automation_id=None):
    from je_auto_control.utils.executor.action_executor import _window_interaction_state
    return _window_interaction_state(name, role, app_name, automation_id)


def legacy_info(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _legacy_info
    return _legacy_info(name, role, app_name, automation_id)


def legacy_default_action(name=None, role=None, app_name=None,
                          automation_id=None):
    from je_auto_control.utils.executor.action_executor import _legacy_default_action
    return _legacy_default_action(name, role, app_name, automation_id)


def get_selection(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_selection
    return _get_selection(name, role, app_name, automation_id)


def list_views(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _list_views
    return _list_views(name, role, app_name, automation_id)


def set_view(view, name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _set_view
    return _set_view(view, name, role, app_name, automation_id)


def wait_for_focus_change(timeout=5.0):
    from je_auto_control.utils.executor.action_executor import _wait_for_focus_change
    return _wait_for_focus_change(timeout)


def get_selected_text(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_selected_text
    return _get_selected_text(name, role, app_name, automation_id)


def get_visible_text(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_visible_text
    return _get_visible_text(name, role, app_name, automation_id)


def _observe_handler(actions):
    from je_auto_control.utils.executor.action_executor import executor

    def handler(_event, _value):
        if actions:
            executor.execute_action(list(actions))
    return handler


def circuit_call(name, actions, threshold=5, reset_s=30.0):
    from je_auto_control.utils.executor.action_executor import _circuit_call
    return _circuit_call(name, actions, threshold=int(threshold),
                         reset_s=float(reset_s))


def run_chaos(spec):
    from je_auto_control.utils.executor.action_executor import _run_chaos
    return _run_chaos(spec)


def bulkhead_run(name, max_concurrent, actions):
    from je_auto_control.utils.executor.action_executor import _bulkhead_run
    return _bulkhead_run(name, max_concurrent, actions)


def trace_inject(headers=None, traceparent=None):
    from je_auto_control.utils.executor.action_executor import _trace_inject
    return _trace_inject(headers, traceparent)


def trace_extract(headers):
    from je_auto_control.utils.executor.action_executor import _trace_extract
    return _trace_extract(headers)


def baggage_parse(header):
    from je_auto_control.utils.executor.action_executor import _baggage_parse
    return _baggage_parse(header)


def baggage_format(items):
    from je_auto_control.utils.executor.action_executor import _baggage_format
    return _baggage_format(items)


def normalize_text(text, form="NFKC", casefold=True, collapse_ws=True):
    from je_auto_control.utils.executor.action_executor import _normalize_text
    return _normalize_text(text, form, casefold, collapse_ws)


def slugify(text, sep="-"):
    from je_auto_control.utils.executor.action_executor import _slugify
    return _slugify(text, sep)


def text_similarity(a, b, metric="jaro_winkler"):
    from je_auto_control.utils.executor.action_executor import _text_similarity
    return _text_similarity(a, b, metric)


def simhash(text, bits=64):
    from je_auto_control.utils.executor.action_executor import _simhash
    return _simhash(text, bits)


def near_duplicates(texts, max_distance=3):
    from je_auto_control.utils.executor.action_executor import _near_duplicates
    return _near_duplicates(texts, max_distance)


def canonical_log(fields):
    from je_auto_control.utils.executor.action_executor import _canonical_log
    return _canonical_log(fields)


def spans_to_otlp(spans, resource_attrs=None):
    from je_auto_control.utils.executor.action_executor import _spans_to_otlp
    return _spans_to_otlp(spans, resource_attrs)


def validate_config(schema, config):
    from je_auto_control.utils.executor.action_executor import _validate_config
    return _validate_config(schema, config)


def resolve_ref(ref):
    from je_auto_control.utils.executor.action_executor import _resolve_ref
    return _resolve_ref(ref)


def resolve_refs(obj):
    from je_auto_control.utils.executor.action_executor import _resolve_refs
    return _resolve_refs(obj)


def parse_link_header(value):
    from je_auto_control.utils.executor.action_executor import _parse_link_header
    return _parse_link_header(value)


def next_url(value):
    from je_auto_control.utils.executor.action_executor import _next_url
    return _next_url(value)


def build_multipart(fields=None, files=None, boundary=None):
    from je_auto_control.utils.executor.action_executor import _build_multipart
    return _build_multipart(fields, files, boundary)


def parse_multipart(content_type, body_base64):
    from je_auto_control.utils.executor.action_executor import _parse_multipart
    return _parse_multipart(content_type, body_base64)


def decode_body(headers, body_base64):
    from je_auto_control.utils.executor.action_executor import _decode_body
    return _decode_body(headers, body_base64)


def parse_quality_values(header):
    from je_auto_control.utils.executor.action_executor import _parse_quality_values
    return _parse_quality_values(header)


def cookie_header(set_cookies):
    from je_auto_control.utils.executor.action_executor import _cookie_header
    return _cookie_header(set_cookies)


def parse_set_cookie(header):
    from je_auto_control.utils.executor.action_executor import _parse_set_cookie
    return _parse_set_cookie(header)


def parse_cache_control(headers):
    from je_auto_control.utils.executor.action_executor import _parse_cache_control
    return _parse_cache_control(headers)


def store_validators(response):
    from je_auto_control.utils.executor.action_executor import _store_validators
    return _store_validators(response)


def redact_config(obj, mask="***"):
    from je_auto_control.utils.executor.action_executor import _redact_config
    return _redact_config(obj, mask)


def redact_secret_text(text, mask="***"):
    from je_auto_control.utils.executor.action_executor import _redact_secret_text
    return _redact_secret_text(text, mask)


def profile_rows(rows, columns=None):
    from je_auto_control.utils.executor.action_executor import _profile_rows
    return _profile_rows(rows, columns)


def infer_schema(rows, columns=None):
    from je_auto_control.utils.executor.action_executor import _infer_schema
    return _infer_schema(rows, columns)


def parse_problem(response):
    from je_auto_control.utils.executor.action_executor import _parse_problem
    return _parse_problem(response)


def parse_dotenv(text):
    from je_auto_control.utils.executor.action_executor import _parse_dotenv
    return _parse_dotenv(text)


def load_dotenv(path, override=False):
    from je_auto_control.utils.executor.action_executor import _load_dotenv
    return _load_dotenv(path, override)


def parse_sse(text):
    from je_auto_control.utils.executor.action_executor import _parse_sse
    return _parse_sse(text)


def resolve_config(layers):
    from je_auto_control.utils.executor.action_executor import _resolve_config
    return _resolve_config(layers)


def explain_config(layers, key):
    from je_auto_control.utils.executor.action_executor import _explain_config
    return _explain_config(layers, key)


def check_compatibility(old, new, mode="backward"):
    from je_auto_control.utils.executor.action_executor import _check_compatibility
    return _check_compatibility(old, new, mode)


def ts_rate(series, window_s=None):
    from je_auto_control.utils.executor.action_executor import _ts_rate
    return _ts_rate(series, window_s)


def ts_downsample(series, bucket_s, agg="avg"):
    from je_auto_control.utils.executor.action_executor import _ts_downsample
    return _ts_downsample(series, bucket_s, agg)


def detect_anomalies(values, method="mad", threshold=None):
    from je_auto_control.utils.executor.action_executor import _detect_anomalies
    return _detect_anomalies(values, method, threshold)


def sma(values, window):
    from je_auto_control.utils.executor.action_executor import _sma
    return _sma(values, window)


def ewma(values, alpha=0.3):
    from je_auto_control.utils.executor.action_executor import _ewma
    return _ewma(values, alpha)


def idempotency_begin(name, key, request=None):
    from je_auto_control.utils.executor.action_executor import _idempotency_begin
    return _idempotency_begin(name, key, request)


def idempotency_complete(name, key, response):
    from je_auto_control.utils.executor.action_executor import _idempotency_complete
    return _idempotency_complete(name, key, response)


def idempotency_release(name, key):
    from je_auto_control.utils.executor.action_executor import _idempotency_release
    return _idempotency_release(name, key)


def dedup_check(name, message_id, ttl_s=3600):
    from je_auto_control.utils.executor.action_executor import _dedup_check
    return _dedup_check(name, message_id, ttl_s)


def sequence_observe(name, stream_id, seq):
    from je_auto_control.utils.executor.action_executor import _sequence_observe
    return _sequence_observe(name, stream_id, seq)


def cas_put(name, key, value, expected_version=None):
    from je_auto_control.utils.executor.action_executor import _cas_put
    return _cas_put(name, key, value, expected_version)


def cas_get(name, key):
    from je_auto_control.utils.executor.action_executor import _cas_get
    return _cas_get(name, key)


def outbox_enqueue(name, event):
    from je_auto_control.utils.executor.action_executor import _outbox_enqueue
    return _outbox_enqueue(name, event)


def outbox_pending(name):
    from je_auto_control.utils.executor.action_executor import _outbox_pending
    return _outbox_pending(name)


def collation_sort(items, strength="tertiary", tailoring=None, reverse=False):
    from je_auto_control.utils.executor.action_executor import _collation_sort
    return _collation_sort(items, strength, tailoring, reverse)


def collation_compare(first, second, strength="tertiary", tailoring=None):
    from je_auto_control.utils.executor.action_executor import _collation_compare
    return _collation_compare(first, second, strength, tailoring)


def confusable_scan(text):
    from je_auto_control.utils.executor.action_executor import _confusable_scan
    return _confusable_scan(text)


def confusable_compare(first, second):
    from je_auto_control.utils.executor.action_executor import _confusable_compare
    return _confusable_compare(first, second)


def readability_report(text):
    from je_auto_control.utils.executor.action_executor import _readability_report
    return _readability_report(text)


def bidi_check(text):
    from je_auto_control.utils.executor.action_executor import _bidi_check
    return _bidi_check(text)


def bidi_strip(text):
    from je_auto_control.utils.executor.action_executor import _bidi_strip
    return _bidi_strip(text)


def format_list(items, style="and", locale="en"):
    from je_auto_control.utils.executor.action_executor import _format_list
    return _format_list(items, style, locale)


def format_message(pattern, args=None, locale="en"):
    from je_auto_control.utils.executor.action_executor import _format_message
    return _format_message(pattern, args, locale)


def gettext_translate(po, msgid, context=None):
    from je_auto_control.utils.executor.action_executor import _gettext_translate
    return _gettext_translate(po, msgid, context)


def gettext_ngettext(po, msgid, msgid_plural, n):
    from je_auto_control.utils.executor.action_executor import _gettext_ngettext
    return _gettext_ngettext(po, msgid, msgid_plural, n)


def checksum_validate(scheme, number):
    from je_auto_control.utils.executor.action_executor import _checksum_validate
    return _checksum_validate(scheme, number)


def checksum_digit(scheme, partial):
    from je_auto_control.utils.executor.action_executor import _checksum_digit
    return _checksum_digit(scheme, partial)


def move_along_path(waypoints, easing="linear", per_segment_steps=20):
    from je_auto_control.utils.executor.action_executor import _move_along_path
    return _move_along_path(waypoints, easing, per_segment_steps)


def drag_path(waypoints, button="mouse_left", easing="linear",
              per_segment_steps=20):
    from je_auto_control.utils.executor.action_executor import _drag_path
    return _drag_path(waypoints, button, easing, per_segment_steps)


def set_field_text(text, clear="select_all", paste=False, modifier="ctrl"):
    from je_auto_control.utils.executor.action_executor import _set_field_text
    return _set_field_text(text, clear, paste, modifier)


def hold_key(key, duration_s=1.0, rate_hz=None):
    from je_auto_control.utils.executor.action_executor import _hold_key
    return _hold_key(key, duration_s, rate_hz)


def move_mouse_relative(dx, dy):
    from je_auto_control.utils.executor.action_executor import _move_mouse_relative
    return _move_mouse_relative(dx, dy)


def input_reachable():
    from je_auto_control.utils.executor.action_executor import (
        _input_reachable,
    )
    return _input_reachable()


def type_unicode(text, modifier="ctrl"):
    from je_auto_control.utils.executor.action_executor import _type_unicode
    return _type_unicode(text, modifier)


def type_unicode_keys(text):
    from je_auto_control.utils.executor.action_executor import _type_unicode_keys
    return _type_unicode_keys(text)


def type_unicode_text(text, modifier="ctrl"):
    from je_auto_control.utils.executor.action_executor import _type_unicode_text
    return _type_unicode_text(text, modifier)


def with_modifiers(modifiers, actions):
    from je_auto_control.utils.executor.action_executor import _with_modifiers
    return _with_modifiers(modifiers, actions)


def grid_cell(boxes, row, col, row_tolerance=10):
    from je_auto_control.utils.executor.action_executor import _grid_cell
    return _grid_cell(boxes, row, col, row_tolerance)


def match_template(template, min_score=0.8, scales=None, region=None,
                   method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_template
    return _match_template(template, min_score, scales, region, method)


def match_template_all(template, min_score=0.8, max_results=20, nms_iou=0.3,
                       region=None):
    from je_auto_control.utils.executor.action_executor import _match_template_all
    return _match_template_all(template, min_score, max_results, nms_iou, region)


def match_masked(template, mask=None, min_score=0.9, region=None):
    from je_auto_control.utils.executor.action_executor import _match_masked
    return _match_masked(template, mask, min_score, region)


def match_masked_all(template, mask=None, min_score=0.9, max_results=20,
                     nms_iou=0.3, region=None):
    from je_auto_control.utils.executor.action_executor import _match_masked_all
    return _match_masked_all(template, mask, min_score, max_results, nms_iou,
                             region)


def match_rotated(template, min_score=0.8, scales=None, angles=None,
                  region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_rotated
    return _match_rotated(template, min_score, scales, angles, region, method)


def match_rotated_all(template, min_score=0.8, scales=None, angles=None,
                      max_results=20, nms_iou=0.3, region=None):
    from je_auto_control.utils.executor.action_executor import _match_rotated_all
    return _match_rotated_all(template, min_score, scales, angles, max_results,
                              nms_iou, region)


def match_with_trust(template, min_score=0.0, scales=None, ambiguous_ratio=0.9,
                     region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_with_trust
    return _match_with_trust(template, min_score, scales, ambiguous_ratio,
                             region, method)


def auto_threshold(template, region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _auto_threshold
    return _auto_threshold(template, region, method)


def match_auto(template, floor=0.5, max_results=20, region=None,
               method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_auto
    return _match_auto(template, floor, max_results, region, method)


def edge_match(template, min_score=0.7, scales=None, region=None):
    from je_auto_control.utils.executor.action_executor import _edge_match
    return _edge_match(template, min_score, scales, region)


def edge_match_all(template, min_score=0.7, max_results=20, nms_iou=0.3,
                   region=None):
    from je_auto_control.utils.executor.action_executor import _edge_match_all
    return _edge_match_all(template, min_score, max_results, nms_iou, region)


def match_subpixel(template, min_score=0.0, region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_subpixel
    return _match_subpixel(template, min_score, region, method)


def vote_centers(centers, agree_px=10, min_votes=2):
    from je_auto_control.utils.executor.action_executor import _vote_centers
    return _vote_centers(centers, agree_px, min_votes)


def match_ensemble(templates, min_score=0.8, agree_px=10, min_votes=2, region=None):
    from je_auto_control.utils.executor.action_executor import _match_ensemble
    return _match_ensemble(templates, min_score, agree_px, min_votes, region)


def match_color(template, channels=None, min_score=0.7, scales=None, region=None):
    from je_auto_control.utils.executor.action_executor import _match_color
    return _match_color(template, channels, min_score, scales, region)


def match_color_all(template, channels=None, min_score=0.7, max_results=20,
                    nms_iou=0.3, region=None):
    from je_auto_control.utils.executor.action_executor import _match_color_all
    return _match_color_all(template, channels, min_score, max_results, nms_iou,
                            region)


def region_stability(frames, settle_threshold=0.99):
    from je_auto_control.utils.executor.action_executor import _region_stability
    return _region_stability(frames, settle_threshold)


def match_persistence(template, frames, min_score=0.8, agree_px=8):
    from je_auto_control.utils.executor.action_executor import _match_persistence
    return _match_persistence(template, frames, min_score, agree_px)


def grid_cells(rows, cols, region=None):
    from je_auto_control.utils.executor.action_executor import _grid_cells
    return _grid_cells(rows, cols, region)


def cell_for_point(x, y, rows, cols, region=None):
    from je_auto_control.utils.executor.action_executor import _cell_for_point
    return _cell_for_point(x, y, rows, cols, region)


def point_for_cell(label, rows, cols, region=None):
    from je_auto_control.utils.executor.action_executor import _point_for_cell
    return _point_for_cell(label, rows, cols, region)


def populate_table(grid, text_boxes, overlap=0.4):
    from je_auto_control.utils.executor.action_executor import _populate_table
    return _populate_table(grid, text_boxes, overlap)


def column_gutters(boxes, page_width=None, min_gap=8):
    from je_auto_control.utils.executor.action_executor import _column_gutters
    return _column_gutters(boxes, page_width, min_gap)


def detect_borderless_table(boxes, page_width=None, min_gap=8, min_cols=2,
                            min_rows=2):
    from je_auto_control.utils.executor.action_executor import _detect_borderless_table
    return _detect_borderless_table(boxes, page_width, min_gap, min_cols, min_rows)


def associate_fields(text_boxes, directions=None, max_gap=150):
    from je_auto_control.utils.executor.action_executor import _associate_fields
    return _associate_fields(text_boxes, directions, max_gap)


def match_labels_to_widgets(labels, widgets):
    from je_auto_control.utils.executor.action_executor import _match_labels_to_widgets
    return _match_labels_to_widgets(labels, widgets)


def flow_order(boxes, min_gap=12):
    from je_auto_control.utils.executor.action_executor import _flow_order
    return _flow_order(boxes, min_gap)


def xy_cut(boxes, min_gap=12):
    from je_auto_control.utils.executor.action_executor import _xy_cut
    return _xy_cut(boxes, min_gap)


def group_paragraphs(lines, line_gap_factor=1.6):
    from je_auto_control.utils.executor.action_executor import _group_paragraphs
    return _group_paragraphs(lines, line_gap_factor)


def detect_lists(lines):
    from je_auto_control.utils.executor.action_executor import _detect_lists
    return _detect_lists(lines)


def classify_lines(lines, heading_ratio=1.2):
    from je_auto_control.utils.executor.action_executor import _classify_lines
    return _classify_lines(lines, heading_ratio)


def outline(lines, heading_ratio=1.2):
    from je_auto_control.utils.executor.action_executor import _outline
    return _outline(lines, heading_ratio)


def find_color_region(rgb, tolerance=20, min_area=50, region=None):
    from je_auto_control.utils.executor.action_executor import _find_color_region
    return _find_color_region(rgb, tolerance, min_area, region)


def ssim_compare(reference, current=None, ignore=None, region=None):
    from je_auto_control.utils.executor.action_executor import _ssim_compare
    return _ssim_compare(reference, current, ignore, region)


def ssim_changed_regions(reference, current=None, ignore=None, threshold=0.35,
                         min_area=50, region=None):
    from je_auto_control.utils.executor.action_executor import _ssim_changed_regions
    return _ssim_changed_regions(reference, current, ignore, threshold, min_area,
                                 region)


def feature_match(template, region=None, max_features=500, ratio=0.75,
                  min_inliers=10):
    from je_auto_control.utils.executor.action_executor import _feature_match
    return _feature_match(template, region, max_features, ratio, min_inliers)


def find_shapes(region=None, min_area=400, max_area=None):
    from je_auto_control.utils.executor.action_executor import _find_shapes
    return _find_shapes(region, min_area, max_area)


def find_rectangles(region=None, min_area=400, max_area=None, aspect_range=None,
                    epsilon=0.04):
    from je_auto_control.utils.executor.action_executor import _find_rectangles
    return _find_rectangles(region, min_area, max_area, aspect_range, epsilon)


def tile_rect(slot, screen=None, gap=0):
    from je_auto_control.utils.executor.action_executor import _tile_rect
    return _tile_rect(slot, screen, gap)


def grid_rects(rows, cols, screen=None, gap=0):
    from je_auto_control.utils.executor.action_executor import _grid_rects
    return _grid_rects(rows, cols, screen, gap)


def cascade_rects(count, screen=None, offset=30, size=None):
    from je_auto_control.utils.executor.action_executor import _cascade_rects
    return _cascade_rects(count, screen, offset, size)


def arrange_grid(titles, rows=None, cols=None, gap=0):
    from je_auto_control.utils.executor.action_executor import _arrange_grid
    return _arrange_grid(titles, rows, cols, gap)


def arrange_cascade(titles, offset=30):
    from je_auto_control.utils.executor.action_executor import _arrange_cascade
    return _arrange_cascade(titles, offset)


def preprocess_image(output_path, source=None, steps=None, scale=2.0, region=None,
                     block_size=31, c=11):
    from je_auto_control.utils.executor.action_executor import _preprocess_image
    return _preprocess_image(output_path, source, steps, scale, region,
                             block_size, c)


def enumerate_monitors():
    from je_auto_control.utils.executor.action_executor import _enumerate_monitors
    return _enumerate_monitors()


def monitor_at_point(x, y):
    from je_auto_control.utils.executor.action_executor import _monitor_at_point
    return _monitor_at_point(x, y)


def wait_actionable(template, timeout_s=5.0, stable_for_s=0.3, min_score=0.8,
                    region=None):
    from je_auto_control.utils.executor.action_executor import _wait_actionable
    return _wait_actionable(template, timeout_s, stable_for_s, min_score, region)


def fuse_elements(ocr=None, icon=None, a11y=None, iou_threshold=0.9):
    from je_auto_control.utils.executor.action_executor import _fuse_elements
    return _fuse_elements(ocr, icon, a11y, iou_threshold)


def reading_order(elements, row_tol=12):
    from je_auto_control.utils.executor.action_executor import _reading_order
    return _reading_order(elements, row_tol)


def segment_hsv(lower_hsv, upper_hsv, min_area=50, region=None):
    from je_auto_control.utils.executor.action_executor import _segment_hsv
    return _segment_hsv(lower_hsv, upper_hsv, min_area, region)


def dominant_hue_regions(hue, hue_tol=10, sat_min=80, val_min=80, min_area=50,
                         region=None):
    from je_auto_control.utils.executor.action_executor import _dominant_hue_regions
    return _dominant_hue_regions(hue, hue_tol, sat_min, val_min, min_area, region)


def find_text_regions(min_area=60, max_area=None, merge=True, max_aspect=12.0,
                      region=None):
    from je_auto_control.utils.executor.action_executor import _find_text_regions
    return _find_text_regions(min_area, max_area, merge, max_aspect, region)


def find_text_lines(y_tolerance=8, region=None):
    from je_auto_control.utils.executor.action_executor import _find_text_lines
    return _find_text_lines(y_tolerance, region)


def find_lines(min_length=80, max_gap=10, orientation="any", region=None):
    from je_auto_control.utils.executor.action_executor import _find_lines
    return _find_lines(min_length, max_gap, orientation, region)


def find_grid(min_length=120, tol=10, region=None):
    from je_auto_control.utils.executor.action_executor import _find_grid
    return _find_grid(min_length, tol, region)


def find_separators(axis="horizontal", min_length=120, tol=10, region=None):
    from je_auto_control.utils.executor.action_executor import _find_separators
    return _find_separators(axis, min_length, tol, region)


def expect_poll(action, key=None, op="truthy", expected=None, timeout_s=5.0,
                interval_s=0.25):
    from je_auto_control.utils.executor.action_executor import _expect_poll
    return _expect_poll(action, key, op, expected, timeout_s, interval_s)


def locate_chain(boxes, ops=None):
    from je_auto_control.utils.executor.action_executor import _locate_chain
    return _locate_chain(boxes, ops)


def set_clipboard_html(html, fragment_plaintext=None):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_html
    return _set_clipboard_html(html, fragment_plaintext)


def get_clipboard_html():
    from je_auto_control.utils.executor.action_executor import _get_clipboard_html
    return _get_clipboard_html()


def set_clipboard_files(paths):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_files
    return _set_clipboard_files(paths)


def get_clipboard_files():
    from je_auto_control.utils.executor.action_executor import _get_clipboard_files
    return _get_clipboard_files()


def set_clipboard_rtf(text):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_rtf
    return _set_clipboard_rtf(text)


def get_clipboard_rtf():
    from je_auto_control.utils.executor.action_executor import _get_clipboard_rtf
    return _get_clipboard_rtf()


def set_clipboard_csv(rows, delimiter=","):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_csv
    return _set_clipboard_csv(rows, delimiter)


def get_clipboard_csv(delimiter=","):
    from je_auto_control.utils.executor.action_executor import _get_clipboard_csv
    return _get_clipboard_csv(delimiter)


def clipboard_formats():
    from je_auto_control.utils.executor.action_executor import _clipboard_formats
    return _clipboard_formats()


def classify_formats(formats):
    from je_auto_control.utils.executor.action_executor import _classify_formats
    return _classify_formats(formats)


def diff_formats(before, after):
    from je_auto_control.utils.executor.action_executor import _diff_formats
    return _diff_formats(before, after)


def plan_file_drop(paths, point=None):
    from je_auto_control.utils.executor.action_executor import _plan_file_drop
    return _plan_file_drop(paths, point)


def drop_files(hwnd, paths, point=None):
    from je_auto_control.utils.executor.action_executor import _drop_files
    return _drop_files(hwnd, paths, point)


def image_quality(source=None, region=None):
    from je_auto_control.utils.executor.action_executor import _image_quality
    return _image_quality(source, region)


def quality_gate(source=None, region=None, min_sharpness=100.0,
                 min_contrast=12.0):
    from je_auto_control.utils.executor.action_executor import _quality_gate
    return _quality_gate(source, region, min_sharpness, min_contrast)


def detect_scale(template, haystack=None, region=None, scales=None,
                 method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _detect_scale
    return _detect_scale(template, haystack, region, scales, method)


def scale_sweep(template, haystack=None, region=None, scales=None,
                method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _scale_sweep
    return _scale_sweep(template, haystack, region, scales, method)


def salient_regions(source=None, region=None, size=64, threshold=None,
                    min_area=4):
    from je_auto_control.utils.executor.action_executor import _salient_regions
    return _salient_regions(source, region, size, threshold, min_area)


def most_salient(source=None, region=None, size=64, threshold=None, min_area=4):
    from je_auto_control.utils.executor.action_executor import _most_salient
    return _most_salient(source, region, size, threshold, min_area)


def failure_signature(error, length=12):
    from je_auto_control.utils.executor.action_executor import _failure_signature
    return _failure_signature(error, length)


def group_failures(errors):
    from je_auto_control.utils.executor.action_executor import _group_failures
    return _group_failures(errors)


def diff_runs(before, after, key="name", regress_factor=1.5):
    from je_auto_control.utils.executor.action_executor import _diff_runs
    return _diff_runs(before, after, key, regress_factor)


def failure_clusters(runs, threshold=0.5, min_size=2):
    from je_auto_control.utils.executor.action_executor import _failure_clusters
    return _failure_clusters(runs, threshold, min_size)


def cofailure_pairs(runs, threshold=0.5):
    from je_auto_control.utils.executor.action_executor import _cofailure_pairs
    return _cofailure_pairs(runs, threshold)


def build_timeline(steps):
    from je_auto_control.utils.executor.action_executor import _build_timeline
    return _build_timeline(steps)


def critical_steps(steps, top=3):
    from je_auto_control.utils.executor.action_executor import _critical_steps
    return _critical_steps(steps, top)


def image_histogram(source=None, bins=32, space="hsv", region=None):
    from je_auto_control.utils.executor.action_executor import _image_histogram
    return _image_histogram(source, bins, space, region)


def histogram_changed(reference, current=None, method="correlation",
                      threshold=0.9, space="hsv", region=None):
    from je_auto_control.utils.executor.action_executor import _histogram_changed
    return _histogram_changed(reference, current, method, threshold, space, region)


def changed_regions(before, after=None, threshold=25, min_area=80, blur=5):
    from je_auto_control.utils.executor.action_executor import _changed_regions
    return _changed_regions(before, after, threshold, min_area, blur)


def has_motion(before, after=None, threshold=25, min_area=80):
    from je_auto_control.utils.executor.action_executor import _has_motion
    return _has_motion(before, after, threshold, min_area)


def set_topmost(title, on=True):
    from je_auto_control.utils.executor.action_executor import _set_topmost
    return _set_topmost(title, on)


def bring_to_front(title):
    from je_auto_control.utils.executor.action_executor import _bring_to_front
    return _bring_to_front(title)


def send_to_back(title):
    from je_auto_control.utils.executor.action_executor import _send_to_back
    return _send_to_back(title)


def soft_assert(checks, raise_on_fail=False):
    from je_auto_control.utils.executor.action_executor import _soft_assert
    return _soft_assert(checks, raise_on_fail)


def perceptual_diff(actual, expected, threshold=0.1, include_aa=False,
                    max_diff_ratio=None):
    from je_auto_control.utils.executor.action_executor import _perceptual_diff
    return _perceptual_diff(actual, expected, threshold, include_aa, max_diff_ratio)


def get_client_rect(title):
    from je_auto_control.utils.executor.action_executor import _get_client_rect
    return _get_client_rect(title)


def client_point(title, x, y):
    from je_auto_control.utils.executor.action_executor import _client_point
    return _client_point(title, x, y)


def cua_command(payload, source="canonical"):
    from je_auto_control.utils.executor.action_executor import _cua_command
    return _cua_command(payload, source)


def serialize_observation(elements, viewport=None, max_elements=80):
    from je_auto_control.utils.executor.action_executor import _serialize_observation
    return _serialize_observation(elements, viewport, max_elements)


def observation_index(elements, viewport=None, max_elements=80):
    from je_auto_control.utils.executor.action_executor import _observation_index
    return _observation_index(elements, viewport, max_elements)


def delta_observation(prev, curr, viewport=None, max_elements=80, max_lines=40,
                      interactive_only=True):
    from je_auto_control.utils.executor.action_executor import _delta_observation
    return _delta_observation(prev, curr, viewport, max_elements, max_lines,
                              interactive_only)


def classify_effect(before, after, action, radius=64):
    from je_auto_control.utils.executor.action_executor import _classify_effect
    return _classify_effect(before, after, action, radius)


def effect_near_point(before, after, point, radius=64):
    from je_auto_control.utils.executor.action_executor import _effect_near_point
    return _effect_near_point(before, after, point, radius)


def check_postcondition(after, spec, before=None):
    from je_auto_control.utils.executor.action_executor import _check_postcondition
    return _check_postcondition(after, spec, before)


def plan_repair(verdict, max_attempts=3):
    from je_auto_control.utils.executor.action_executor import _plan_repair
    return _plan_repair(verdict, max_attempts)


def consensus_point(candidates, cluster_radius=24):
    from je_auto_control.utils.executor.action_executor import _consensus_point
    return _consensus_point(candidates, cluster_radius)


def consensus_element(candidates, elements):
    from je_auto_control.utils.executor.action_executor import _consensus_element
    return _consensus_element(candidates, elements)


def settle_point(churns, quiet_samples=3, max_churn=1.0):
    from je_auto_control.utils.executor.action_executor import _settle_point
    return _settle_point(churns, quiet_samples, max_churn)


def build_critic_record(action, before, after, postcondition=None, radius=64):
    from je_auto_control.utils.executor.action_executor import _build_critic_record
    return _build_critic_record(action, before, after, postcondition, radius)


def score_step(record):
    from je_auto_control.utils.executor.action_executor import _score_step
    return _score_step(record)


def validate_action(action, screen=None, targets=None):
    from je_auto_control.utils.executor.action_executor import _validate_action
    return _validate_action(action, screen, targets)


def replay_trace(trace):
    from je_auto_control.utils.executor.action_executor import _replay_trace
    return _replay_trace(trace)


def match_elements(before, after, iou_threshold=0.5):
    from je_auto_control.utils.executor.action_executor import _match_elements
    return _match_elements(before, after, iou_threshold)


def assign_stable_ids(elements, prior=None, iou_threshold=0.5):
    from je_auto_control.utils.executor.action_executor import _assign_stable_ids
    return _assign_stable_ids(elements, prior, iou_threshold)


def score_candidates(candidates, want_role=None, want_name=None, anchor=None):
    from je_auto_control.utils.executor.action_executor import _score_candidates
    return _score_candidates(candidates, want_role, want_name, anchor)


def best_candidate(candidates, want_role=None, want_name=None, anchor=None):
    from je_auto_control.utils.executor.action_executor import _best_candidate
    return _best_candidate(candidates, want_role, want_name, anchor)


def read_barcodes(source=None, region=None):
    from je_auto_control.utils.executor.action_executor import _read_barcodes
    return _read_barcodes(source, region)


def detect_drift(reference, current, threshold=0.25, bins=10):
    from je_auto_control.utils.executor.action_executor import _detect_drift
    return _detect_drift(reference, current, threshold, bins)


def categorical_drift(reference, current):
    from je_auto_control.utils.executor.action_executor import _categorical_drift
    return _categorical_drift(reference, current)


def diff_rows(old_rows, new_rows, key):
    from je_auto_control.utils.executor.action_executor import _diff_rows
    return _diff_rows(old_rows, new_rows, key)


def cell_changes(old_rows, new_rows, key):
    from je_auto_control.utils.executor.action_executor import _cell_changes
    return _cell_changes(old_rows, new_rows, key)


def check_foreign_key(child_rows, child_col, parent_rows, parent_col):
    from je_auto_control.utils.executor.action_executor import _check_foreign_key
    return _check_foreign_key(child_rows, child_col, parent_rows, parent_col)


def check_unique_key(rows, cols):
    from je_auto_control.utils.executor.action_executor import _check_unique_key
    return _check_unique_key(rows, cols)


def check_accepted_values(rows, col, allowed):
    from je_auto_control.utils.executor.action_executor import _check_accepted_values
    return _check_accepted_values(rows, col, allowed)


def check_row_count(rows, minimum=None, maximum=None):
    from je_auto_control.utils.executor.action_executor import _check_row_count
    return _check_row_count(rows, minimum, maximum)


def walk_tree(app_name=None, max_results: int = 500):
    from je_auto_control.utils.executor.action_executor import _walk_tree
    return _walk_tree(app_name, max_results)


def humanize_role(role):
    from je_auto_control.utils.executor.action_executor import _humanize_role
    return _humanize_role(role)


def tab_order(app_name=None, max_results: int = 500):
    from je_auto_control.utils.executor.action_executor import _tab_order
    return _tab_order(app_name, max_results)


def audit_focus_order(app_name=None, max_results: int = 500):
    from je_auto_control.utils.executor.action_executor import _audit_focus_order
    return _audit_focus_order(app_name, max_results)


def focus_control(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _focus_control
    return _focus_control(name, role, app_name, automation_id)


def a11y_record_start(app_name: Optional[str] = None,
                      poll_interval_s: float = 0.25,
                      min_movement_px: int = 8) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import (
        _a11y_record_start,
    )
    return _a11y_record_start(
        app_name=app_name,
        poll_interval_s=float(poll_interval_s),
        min_movement_px=int(min_movement_px),
    )


def a11y_record_stop() -> List[Dict[str, Any]]:
    from je_auto_control.utils.executor.action_executor import (
        _a11y_record_stop,
    )
    return _a11y_record_stop()


def wait_image_gone(image, detect_threshold: float = 1.0,
                    timeout_s: float = 10.0, poll_interval_s: float = 0.2,
                    gone_for_s: float = 0.0) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _wait_image_gone
    return _wait_image_gone(image, detect_threshold, timeout_s,
                            poll_interval_s, gone_for_s)


def wait_text_gone(text: str, timeout_s: float = 10.0,
                   poll_interval_s: float = 0.2,
                   gone_for_s: float = 0.0) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _wait_text_gone
    return _wait_text_gone(text, timeout_s, poll_interval_s, gone_for_s)


def wait_color(target_rgb, region=None, tolerance=10, min_fraction=0.5,
               present=True, timeout_s=10.0, poll_interval_s=0.2):
    from je_auto_control.utils.executor.action_executor import _wait_color
    return _wait_color(target_rgb, region, tolerance, min_fraction,
                       present, timeout_s, poll_interval_s)


def wait_window_title(pattern, present=True, regex=True, timeout_s=10.0,
                      poll_interval_s=0.2):
    from je_auto_control.utils.executor.action_executor import _wait_window_title
    return _wait_window_title(pattern, present, regex, timeout_s,
                              poll_interval_s)


def anchor_locate(anchor: Dict[str, Any], target: Dict[str, Any],
                  relation: str = "near",
                  max_distance_px: float = 200.0,
                  ordinal: int = 1) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _anchor_locate
    return _anchor_locate(anchor, target, relation, max_distance_px, ordinal)


def anchor_locate_all(anchor: Dict[str, Any], target: Dict[str, Any],
                      relation: str = "near",
                      max_distance_px: float = 200.0) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _anchor_locate_all
    return _anchor_locate_all(anchor, target, relation, max_distance_px)


def run_agent(goal: str,
              backend: str = "anthropic",
              max_steps: int = 25,
              wall_seconds: float = 300.0,
              model: Optional[str] = None,
              max_tokens: int = 1024) -> Dict[str, Any]:
    """Drive the generic plan→act→verify→retry AgentLoop against ``goal``."""
    from je_auto_control.utils.executor.action_executor import _run_agent
    return _run_agent(
        goal=goal, backend=backend,
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
        model=model, max_tokens=int(max_tokens),
    )


def redact_screenshot(file_path: str,
                      output_path: Optional[str] = None,
                      policy: str = "moderate",
                      regions: Optional[List[List[int]]] = None,
                      accessibility: Optional[List[Dict[str, Any]]] = None,
                      ocr: Optional[List[Dict[str, Any]]] = None,
                      ) -> Dict[str, Any]:
    """Blur PII regions in a saved screenshot via the redaction engine."""
    from je_auto_control.utils.executor.action_executor import (
        _redact_screenshot,
    )
    return _redact_screenshot(
        file_path=file_path, output_path=output_path,
        policy=policy, regions=regions,
        accessibility=accessibility, ocr=ocr,
    )


def android_find_element(text: Optional[str] = None,
                         resource_id: Optional[str] = None,
                         description: Optional[str] = None,
                         class_name: Optional[str] = None,
                         timeout_s: float = 5.0,
                         serial: Optional[str] = None,
                         ) -> Dict[str, int]:
    """Find an Android widget via uiautomator2; return its bounding rect."""
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_find_element,
    )
    return _ac_android_find_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=timeout_s, serial=serial,
    )


def android_click_element(text: Optional[str] = None,
                          resource_id: Optional[str] = None,
                          description: Optional[str] = None,
                          class_name: Optional[str] = None,
                          timeout_s: float = 5.0,
                          serial: Optional[str] = None,
                          ) -> Dict[str, int]:
    """Tap the first widget matching the selectors; return click centre."""
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_click_element,
    )
    return _ac_android_click_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=timeout_s, serial=serial,
    )


def android_dump_hierarchy(serial: Optional[str] = None) -> str:
    """Return the device's widget tree as an XML string."""
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_dump_hierarchy,
    )
    return _ac_android_dump_hierarchy(serial=serial)


def ios_tap(x: int, y: int,
            url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.utils.executor.action_executor import _ac_ios_tap
    return _ac_ios_tap(x=int(x), y=int(y), url=url)


def ios_swipe(x1: int, y1: int, x2: int, y2: int,
              duration_s: float = 0.5,
              url: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _ac_ios_swipe
    return _ac_ios_swipe(x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                          duration_s=float(duration_s), url=url)


def ios_type(text: str, url: Optional[str] = None) -> str:
    from je_auto_control.utils.executor.action_executor import _ac_ios_type
    return _ac_ios_type(text=text, url=url)


def ios_screenshot(file_path: str, url: Optional[str] = None) -> str:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_screenshot,
    )
    return _ac_ios_screenshot(file_path=file_path, url=url)


def ios_find_element(name: Optional[str] = None,
                     class_name: Optional[str] = None,
                     predicate: Optional[str] = None,
                     timeout_s: float = 5.0,
                     url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_find_element,
    )
    return _ac_ios_find_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=float(timeout_s), url=url,
    )


def ios_click_element(name: Optional[str] = None,
                      class_name: Optional[str] = None,
                      predicate: Optional[str] = None,
                      timeout_s: float = 5.0,
                      url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_click_element,
    )
    return _ac_ios_click_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=float(timeout_s), url=url,
    )


def ios_dump_source(url: Optional[str] = None) -> str:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_dump_source,
    )
    return _ac_ios_dump_source(url=url)
