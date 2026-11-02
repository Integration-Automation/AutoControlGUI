"""Reviewable file-only template revisions, fixed-frame verification and guarded transitions."""
import base64
import json
from typing import Any, Callable, Optional

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, READ_ONLY, MCPContent, MCPTool, schema

_Definition = tuple[str, Callable[..., Any], dict[str, Any], list[str], bool, str]


def _progress(ctx: Optional[ToolCallContext]) -> Callable[[int], None]:
    count = 0
    def checkpoint(_value: int) -> None:
        nonlocal count
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(count, message="Template candidate checkpoint")
            count += 1
            ctx.check_cancelled()
    return checkpoint


def _create(template_path: str, candidate_path: str, bundle_path: str, threshold: float = 0.9, *,
               ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    # pylint: disable-next=import-outside-toplevel  # reason: business imports remain lazy during registry setup
    from je_auto_control.utils.self_healing.template_commands import _create_from_file
    result = _create_from_file(template_path, candidate_path, bundle_path, threshold,
                                observer=_progress(ctx), path_policy=ctx.path_policy if ctx is not None else None)
    return result.to_dict()


def _preview(bundle_path: str, *, ctx: Optional[ToolCallContext] = None) -> list[MCPContent]:
    # pylint: disable-next=import-outside-toplevel  # reason: codecs load only after an explicit preview request
    from je_auto_control.utils.self_healing.template_candidates import preview_template_candidate
    result = preview_template_candidate(bundle_path, observer=_progress(ctx),
                                          path_policy=ctx.path_policy if ctx is not None else None)
    return [MCPContent.text_block(json.dumps(result.to_dict(), ensure_ascii=False)),
            MCPContent.image_block(base64.b64encode(result.original_png).decode("ascii")),
            MCPContent.image_block(base64.b64encode(result.candidate_png).decode("ascii"))]


def _verify(bundle_path: str, dataset_path: str, *,
               ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    # pylint: disable-next=import-outside-toplevel  # reason: evaluator imports are deferred until tool execution
    from je_auto_control.utils.self_healing.template_candidates import verify_template_candidate
    return verify_template_candidate(bundle_path, dataset_path, observer=_progress(ctx),
                                       path_policy=ctx.path_policy if ctx is not None else None).to_dict()


def _accept(bundle_path: str, dataset_path: str, expected_revision: str, *,
               ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    # pylint: disable-next=import-outside-toplevel  # reason: mutation code loads only for explicit acceptance
    from je_auto_control.utils.self_healing.template_candidates import accept_template_candidate
    return accept_template_candidate(bundle_path, dataset_path, expected_revision, observer=_progress(ctx),
                                       path_policy=ctx.path_policy if ctx is not None else None).to_dict()


def _revert(bundle_path: str, expected_revision: str, *,
               ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    # pylint: disable-next=import-outside-toplevel  # reason: mutation code loads only for explicit rollback
    from je_auto_control.utils.self_healing.template_candidates import revert_template_candidate
    return revert_template_candidate(bundle_path, expected_revision, observer=_progress(ctx),
                                       path_policy=ctx.path_policy if ctx is not None else None).to_dict()


def template_candidate_tools() -> list[MCPTool]:
    """Expose explicit file actions; verification uses frozen local pixels and never a live VLM."""
    path = {"type": "string", "format": "path"}
    revision = {"type": "string", "minLength": 64, "maxLength": 64}
    definitions: list[_Definition] = [
        ("create", _create, {"template_path": path, "candidate_path": path, "bundle_path": path,
                             "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.9}},
         ["template_path", "candidate_path", "bundle_path"], False,
         "Save original and supplied candidate PNG in a new immutable bundle; active template stays unchanged."),
        ("preview", _preview, {"bundle_path": path}, ["bundle_path"], True,
         "Preview original/candidate thumbnails and revision metadata; images are capped at 512 pixels per side."),
        ("verify", _verify, {"bundle_path": path, "dataset_path": path}, ["bundle_path", "dataset_path"], True,
         "Compare frozen versions on a local sample manifest. Eligibility requires labelled hits and misses, "
         "all labelled cases correct; unknowns stay unknown. Dataset versions are unused."),
        ("accept", _accept, {"bundle_path": path, "dataset_path": path, "expected_revision": revision},
         ["bundle_path", "dataset_path", "expected_revision"], False,
         "Reverify the reviewed bundle then atomically activate it, refusing intervening file edits."),
        ("revert", _revert, {"bundle_path": path, "expected_revision": revision},
         ["bundle_path", "expected_revision"], False,
         "Restore original bytes only when this exact candidate is active; later edits are conflicts."),
    ]
    return [MCPTool(name=f"ac_template_candidate_{name}", description=description,
                    input_schema=schema(properties, required=required), handler=handler,
                    annotations=READ_ONLY if readonly else DESTRUCTIVE)
            for name, handler, properties, required, readonly, description in definitions]
