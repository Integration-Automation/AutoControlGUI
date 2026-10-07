# Modernization acceptance evidence

Run controlled integration with:

```sh
python test/verify/modernization_verify.py --output acceptance-evidence
```

The report names platform, backend, Python/package versions, source commit,
actual results and artifact paths. Successful checks require existing evidence
files; skipped checks require reasons. Journal replay uses only a patched executor
device sink. SQLite restart proves durable revision and retry, without claiming
network convergence. The GUI test renders the reopened result offscreen. Each
journal run has a fresh identity so reusing an artifact directory does not mix runs.

`quality.yml` runs coverage with the unchanged floor for Python 3.10–3.14 on
Windows, Linux and macOS. The separate extras typing job installs actual Qt and
mobile SDK packages. Coverage startup precedes pytest plugins. Python 3.10 native
crash diagnostics retain debugger output. Controlled reports are uploaded per job.

`platform-smoke.yml` accepts manual dispatch and includes Windows/Linux/macOS,
Linux arm64 and Windows arm64 stable API/image checks. The macOS native verifier
adds `--output macos-native-report.json`: actual probe failures stay failures in
both JSON and the process exit status. Native checks run on the CI runner only.

## Retained container evidence

| Evidence | Source | Scope |
| --- | --- | --- |
| [D3 Docker](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37595864748) | `255f3d99` | Sway/kernel input, EIS/libei/RemoteDesktop and private D-Bus lifecycle |
| [Android Docker](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37625736780) | `21e02733` | Android 14 emulator launch, 1440×3040 capture and named stop |
| [E4 quality](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37625917081) | `21e02733` | Nine platform/Python coverage and type jobs; earlier security findings retained in that run |

These runs retain their original source revisions. They do not claim to test later
changes. The final H3 runs and local measurements are recorded in the update log.
Docker verifies native compositor/protocol behavior and Android emulator behavior;
human consent timing, physical input restoration and physical mobile acceptance
still require their respective environments.

## Downstream boundary

The read-only H3 test run loaded the modernization branch explicitly, without
reinstalling the production editable package: 742 passed, one expected failure and
one failing legacy `slash` expectation. The prepared migration patch applies to a
temporary copy; all 13 related shortcut cases pass there. The production copy is
left intact. Final merge/application acceptance waits for active processes to
finish, as required by [Progress.md](../Progress.md).

Other pending evidence includes real recording output, mixed DPI/Retina behavior,
GNOME/KDE consent and held-key recovery, Android Unicode/focus/rotation/IME recovery,
exclusive remote WDA session/client races and two-host sync/transport panel closure.
Upstream libei pause/sequence/half-open teardown issues and unavailable Windows
arm64 OpenCV/crypto wheels remain explicitly tracked in Progress. Controlled
fixtures and passing CI jobs do not remove those conditions.

## Local H3 regression result

Windows/Python 3.14.4 full run preceding the remote-viewer CI correction: 11,483 passed, 46 skipped, 591.99 seconds; coverage 87.00% with the unchanged floor. That revision's wheel imports with Qt and all heavy image/crypto packages blocked, retains 822 commands/1,403 names and compiles generated Python. Wheel SHA256: `41fe3ae5d9f8bcc57b0fb3abe8d207e7ca782d128bcc8e6fae178540bb6ca05a`.

The first H3 quality dispatch at `9675a98f` revealed that the base type gate omitted the optional Qt companion `shiboken6`. It is now a precise third-party boundary; extras checking removes both Qt and companion skips to use installed real stubs. No business-module exemption or global ignore is added. Diagnostics print the actual type errors in either mode. All three local stable/extras targets pass; CI rerun evidence is recorded in updates.

The first fifteen-target CI run exposed missing Xvfb in the Linux evidence step, a delayed ready callback in the ownership test and an early remote JPEG arriving before its window exists. The viewer now retains only the latest early image and clears it on disconnect. Controlled reconnect tests protect replacement owners; 64 GUI/task/transport regressions pass, including the new two-case frame test. The evidence step runs under Xvfb on Linux. Private-bus setup checks installed dependencies first and bounds apt acquisition retries after an Azure mirror timeout.

[H3 platform smoke](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37677922126) at `9675a98f` passed all eleven jobs, including native macOS and arm64. [H3 Docker](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37677931015) passed all six selected native verification/build jobs; full-image headless and X11 jobs were outside the selected D3 scope.

[H3 Android Docker](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37681934892)
at `a4e9e2b3` passed on Android 14 with uiautomator2 3.7.0 and adbutils 2.12.0.
The observed Settings app starts, supplies a 1440×3040 frame and stops. Visual
inspection confirms the Settings page in that frame. The original
[mobile report](validation/h3-android-native.json) records the untested
Unicode/focus/rotation/IME restoration explicitly.

The second quality run passed fourteen coverage jobs; Windows 3.13 exposed an
existing test checking resource shutdown before its asynchronous completion.
It now waits for the same asserted shutdown order and always clears substitutes.
All forty ownership cases and thirty repeated cleanup checks pass; final full
matrix evidence follows in the update log.

The third quality run at `0723f8f2` likewise passes fourteen coverage jobs.
Windows 3.11 catches another old immediate assertion: the Window Manager test
must wait for its initial refresh before inserting selected rows, then for focus
and close completion. The same selected-window assertion remains; 46 related
cases pass with one optional skip, and thirty repeated selected-window checks pass.
Package code is unchanged by these two test timing corrections.

The release wheel after the viewer correction passes the same isolated import
and generated-code compilation checks. All 1,200 packaged Python/type files match
the current source. Its SHA256 is
`e6bd35ae9a070aa9cbe3c5c024d41978bfc3b92dd0d4afe987f52343910008d3`;
the [wheel report](validation/h3-release-wheel.json) identifies its package source.
The sdist also builds successfully. The
[native manifest](validation/h3-native-manifest.json) links each native run to its
source and preserves checked Docker summaries and artifact hashes.
