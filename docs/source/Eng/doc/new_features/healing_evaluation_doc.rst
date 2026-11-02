Fixed-frame locator comparison
==============================

The experimental evaluator compares versions on identical immutable PNG inputs::

    from je_auto_control import evaluate_healing_manifest, write_healing_report

    report = evaluate_healing_manifest("benchmarks/self_healing/dataset.json")
    write_healing_report(report, "locator-comparison.json")
    write_healing_report(report, "locator-comparison.html")

``AC_self_heal_evaluate`` and MCP ``ac_self_heal_evaluate`` take a ``path``
to the same local manifest. The CLI runs the AC command from an action JSON file.
Script Builder includes it. **Self-Healing → Version comparison** provides
background comparison, cancellation, case/provenance details and export through Actions.
Changing the manifest discards old results; closing the panel requests stop.

Schema 1 has ``samples`` and ``versions``. Sample fields are ``id``, ``frame``,
optional ``expected_box``, ``expected_miss``, ``origin``, ``scale``, ``region``,
``run_id`` and ``step_id``. A version has ``template`` and optional ``threshold``.
Assets are relative to the manifest directory and may not escape it, including
through symlinks. Explicit and enclosing journal path policies intersect.
Manifest/file/pixel limits are 1 MiB, 16 MiB/16 million pixels per PNG and 64 MiB
encoded assets total; at most 500 samples, 32 versions and 10,000 pairs.

Boxes are half-open logical screen coordinates; scale means pixels per logical
unit. Negative origins and regions are supported. Unknown labels are separate
from expected misses. Accuracy uses labelled samples; false positives use
labelled predictions. Recovery requires a correct point and explicit operation
verification, among fallback attempts with known labels and verification.
Every ratio includes numerator/denominator; empty populations have null values.
The adapters never operate a device or invent verification. Optional costs are
USD with a known-cost count. PNG payloads are excluded from reports.

For Python strategies, use ``EvaluationSample``, ``TemplateFrameLocator``,
``VLMFrameLocator`` and ``evaluate_locators``. VLM requires an explicitly supplied
backend; manifests never select one. Tests use a fake backend. Exceptions and
cancellation propagate without being reported as misses. Known run-local secrets
are masked in report snapshots without mutating inputs.

The version-controlled synthetic dataset and acceptance populations live in
``benchmarks/self_healing``. It covers changed templates, misses, unknown labels,
negative origin, 2× scale and cropping. It does not establish real-application
accuracy. p50/p95 use linear interpolation of wall times including decode/lazy
imports, without warm-up or machine normalization; no speed improvement is claimed.
