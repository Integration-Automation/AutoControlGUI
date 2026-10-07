# GUI F4 reference evidence

Actual Qt offscreen renders and fresh-process measurements on Windows 11 build
26300 / Python 3.14.4 / PySide 6.11.1; installed Segoe UI and Microsoft JhengHei
fonts are loaded by path. No font files are redistributed. Native desktop,
physical input, permissions and actual mixed-monitor DPI remain H3 acceptance.

`before.json` targets E4 commit 21e027334a7af4a808682f03e20c70f0075a5f23;
`after.json` targets F3 commit 09ebb5f16417e0424928e940769ab05282aae68f.
Both retain one warmup and three fresh-process samples with identical settings.
`*-initial.json` retain the earlier zero-warmup run, including the first baseline
startup of 18.45 seconds. They are not used to calibrate the warmed comparison.
`module_path` confirms the target checkout; the production editable checkout
was never imported or reinstalled for these runs.

| Median metric | Before | After |
| --- | ---: | ---: |
| Main window startup (ms) | 6698.29 | 5894.36 |
| Python tracemalloc startup peak (bytes; not RSS) | 100860561 | 90167341 |
| First Mobile panel open (ms) | 19.37 | 22.81 |
| Event loop p95 during real AC_sleep(.25) (ms) | 263.16 | 16.33 |

Lazy panel opening has a visible first-open cost. Only three samples were taken;
these figures do not establish statistical significance or native-platform speed.
The p95 is nearest-rank across the QTimer gaps in each run, then the median across
runs. Baseline execution blocks the GUI and produces only four gaps; the worker
version keeps sampling during the same executor sleep.

`budgets.json` checks startup/memory median ratios <=1.10, first-open <=50 ms
(observed maximum <24 ms with headroom), event-loop p95 <=25 ms (observed
maximum <18 ms with headroom). These are calibrated reference limits, not a
universal CI hardware threshold. Comparison rejects a different environment or
workload. `comparison.json` retains the checks and their observed values.

```powershell
python benchmarks/gui_startup.py --project-root <checkout> --runs 3 --warmup 1 --font C:/Windows/Fonts/segoeui.ttf --font C:/Windows/Fonts/msjh.ttc --output <report.json>
python benchmarks/gui_startup.py --compare benchmarks/results/gui-workspace-f4/before.json benchmarks/results/gui-workspace-f4/after.json --budget benchmarks/results/gui-workspace-f4/budgets.json --output <comparison.json>
python benchmarks/gui_workspace_capture.py --output <captures> --tasks --font C:/Windows/Fonts/segoeui.ttf --font C:/Windows/Fonts/msjh.ttc
```

`layouts/` contains six actual Qt frames: dark English, light Chinese, 640x480
Chinese (395 logical-pixel scrollable workspace), busy Script, cancelled Script
and invalid-JSON error. Cancellation is captured after the owned job returns.
`test_gui_feature_parity.py` verifies all 50 catalog keys, default workflow,
unavailable-feature reason, synthetic mixed-DPI transforms and Qt-free imports.
Menu/navigation/lifecycle regressions cover keyboard Actions, close and cancel.
Synthetic screens and offscreen images do not certify actual monitors.
