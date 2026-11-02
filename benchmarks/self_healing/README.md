# Fixed-frame locator comparison

Run from the repository root with the project's Python environment:

```python
from je_auto_control import evaluate_healing_manifest, write_healing_report

report = evaluate_healing_manifest("benchmarks/self_healing/dataset.json")
write_healing_report(report, "locator-comparison.json")
write_healing_report(report, "locator-comparison.html")
```

The five synthetic PNG samples cover an old template, a changed template, a negative origin with 2× scale and a region, an expected miss, and an unlabelled frame. `acceptance.json` fixes the expected populations: old 2/4 correct, new 3/4, one unknown each, no false positives. This tiny regression dataset does not establish accuracy on real applications. Rebuild its PNGs with `python benchmarks/self_healing/build_fixtures.py`; `Random` seeds and pixel dimensions are fixed.

The same report is available through `AC_self_heal_evaluate` with `{"path":"benchmarks/self_healing/dataset.json"}`, MCP `ac_self_heal_evaluate`, Script Builder, and **Self-Healing → Version comparison**. The CLI can execute an action JSON file containing that command. GUI operations live in Actions; comparison runs in a cancellable worker and changing the manifest discards old results. JSON and standalone HTML exports contain case labels, coordinates, frame hashes and run/step provenance, but no PNG payloads.

Manifest schema 1 requires `samples` and `versions`. A sample has `id`, relative `frame`, optional `expected_box`, `expected_miss`, `origin`, `scale`, `region`, `run_id`, `step_id`. Boxes are half-open `[left, top, right, bottom]` in logical screen units; `scale` is pixels per logical unit. A box and expected miss cannot coexist. No label means unknown. Region pixels are cropped identically for both strategies; transformed pointer coordinates are floored. A version has a relative `template` PNG and optional `threshold` (default 0.9). Absolute assets, directory traversal and symlink escapes are refused. Explicit/enclosing path policies intersect. Limits: 1 MiB manifest, 16 MiB/16 million pixels per PNG, 64 MiB encoded assets total, 500 samples, 32 versions and 10,000 sample/version pairs. Unknown fields, duplicate JSON keys, invalid numbers and constant templates fail explicitly. No capture, input or network backend is selected by this manifest operation.

For custom Python comparisons, use `EvaluationSample`, `TemplateFrameLocator` and `evaluate_locators(samples, versions)`. `VLMFrameLocator` requires an explicitly supplied `VLMBackend`; it never calls `get_backend`. Its coordinates are local PNG pixels and use the same region/origin/scale transform. An optional template fallback receives the identical immutable sample. Tests use a controlled backend; no paid service acceptance is claimed. Backend exceptions and cancellation propagate without becoming misses or partial reports.

Every ratio includes numerator, denominator and a null value for an empty eligible population:

| Metric | Numerator | Denominator |
| --- | --- | --- |
| Accuracy | Correct point in labelled box, or a correct expected miss | Labelled samples |
| False positive | Wrong detected point or unexpected detection | Labelled samples returning coordinates |
| Recovery | Correct detected point **and** explicit `verified=True` | Fallback attempts with a known label and explicit verification result |
| Image hit / fallback / miss | Corresponding observed strategy outcome | All attempts |

Unlabelled samples never count as correct. A model point or an expected miss cannot count as recovery. Missing labels/verification remain explicit unknowns. `verification_unknown` counts fallback attempts missing either a ground-truth label or an explicit verification result; `unknown` counts unlabelled samples independently. Verification is evidence supplied by the caller; these offline adapters never perform an operation or invent verification. Optional costs are USD, with the known-cost population shown; unavailable costs stay null. p50/p95 use linearly interpolated wall time across the samples, including PNG decoding and initial lazy imports, with no warm-up or machine-normalization. These small samples do not support a latency improvement claim. Per-strategy timings retain nested fallback names. Reports mask already-resolved run-local secret strings without changing caller inputs.
