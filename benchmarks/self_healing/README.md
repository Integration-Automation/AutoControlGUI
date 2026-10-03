# Fixed-frame self-healing comparison

Run from the repository with the installed package:

```powershell
python benchmarks/self_healing/compare.py --report .test-tmp/healing-report.json
```

The five synthetic samples cover a changed template, a negative desktop origin,
pixel-to-logical scaling, an expected miss and an unlabelled frame. Every version
reads the same bytes. `build_fixtures.py` deterministically rebuilds the committed
PNG assets and dataset. No screenshot, click or paid model call is made.

The baseline has labelled accuracy 1/4; the candidate has 4/4. Unknown samples are
excluded. Accuracy includes correctly labelled negatives. False-positive rate
uses labelled predictions with returned coordinates. Recovery uses labelled
positive VLM attempts, including errors; wrong guesses never count as recovery.
p50/p95 use linear interpolation over all attempt latencies. Cost stays unknown
unless a strategy supplies a measured value. Historical operation verification
belongs to the original run and is not transferred to a compared version.

JSON retains each frame hash, expected box, origin, scale and optional original
run/step context. HTML provides metric and failure tables plus the same full
evidence. Timings vary by machine; this dataset is offline contract evidence,
not physical-device or model-quality evidence.

For template changes, call `create_template_candidate`, review
`preview_template_candidate`, and run `validate_template_candidate` on labelled
data. Acceptance requires perfect labelled accuracy, no errors/false positives
and at least one correct positive hit. `accept_template_candidate` checks the
baseline hash before replacing it; `revert_template_revision` restores that
baseline only if the accepted candidate remains current. Preview never accepts
or replaces a template.
