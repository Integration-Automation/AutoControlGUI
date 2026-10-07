# Mobile setup and smoke

Install the package and GUI extra in your isolated environment, then install optional
`uiautomator2==3.7.0` (Android) or `facebook-wda==1.5.4` (iOS). Neither SDK is
required for passive context/capability inspection. Do not change a running editable
consumer's environment to test this branch.

## Android emulator or physical device

Install Android SDK platform-tools, enable USB debugging and accept the device's RSA
authorization dialog. `adb devices -l` must show the selected serial as `device`.
`unauthorized` means authorization is missing, not successful input. Set `adb_path`
when platform-tools is not on PATH. SDK bootstrap can install its own helper;
use a disposable test device and an adequate bounded context timeout.

```sh
python examples/mobile_device_smoke.py --validate
python examples/mobile_device_smoke.py --platform android --target emulator-5554 --connect
python examples/mobile_device_smoke.py --platform android --target emulator-5554 --connect --exercise --app-id com.android.settings --output mobile-smoke.png
```

Exercise explicitly starts/stops the named app and captures its device frame. It does
not test Unicode focus, rotation, IME/clipboard recovery or physical keyboard input.
Choose an installed disposable app; app stop is intentional and does not restore an
earlier app state. Capture failure still attempts observed app stop.

## Docker / Linux KVM

The pinned Android 14/API 34 image is the public Docker-Android v3.7.0-p1 release.
Run on a Linux Docker host with usable `/dev/kvm`; Windows needs a Linux VM/WSL
configuration supporting nested virtualization. Docker configuration alone cannot
provide KVM. No physical device/user directory is mounted; ADB listens on loopback.

```sh
docker compose -f docker/mobile-compose.yml up -d
adb connect 127.0.0.1:5555
adb -s 127.0.0.1:5555 shell getprop sys.boot_completed
python examples/mobile_device_smoke.py --platform android --target 127.0.0.1:5555 --connect --exercise --app-id com.android.settings --output mobile-smoke.png
docker compose -f docker/mobile-compose.yml down
```

Wait for boot_completed=1 before exercise. `.github/workflows/mobile-smoke.yml`
performs this on an isolated GitHub Linux runner and saves JSON, PNG and emulator
logs, including ADB/SDK package versions. The workflow fixes adbutils==2.12.0 and
retry2==0.9.5 to preserve the SDK transport contract. Only a successful run artifact is native emulator evidence; this configuration
is not physical-device evidence. Container details follow the upstream
[Docker-Android setup](https://github.com/budtmo/docker-android) and
[host ADB connection guide](https://github.com/budtmo/docker-android/blob/master/documentations/USE_CASE_CONTROL_EMULATOR.md).

## Remote iOS WDA

Build/sign WebDriverAgentRunner on an Apple host using Xcode and your development
team/device provisioning. Enable Developer Mode where required, trust the developer,
and start the runner on the selected device/simulator. Expose its URL through a
trusted tunnel/network; signing and iOS native execution cannot be supplied by this
Linux Android container. Follow the official
[WDA setup](https://github.com/appium/WebDriverAgent).

```sh
python examples/mobile_device_smoke.py --platform ios --target http://127.0.0.1:8100 --connect
python examples/mobile_device_smoke.py --platform ios --target http://127.0.0.1:8100 --connect --exercise --app-id com.example.demo --output ios-smoke.png
```

GET /status reports HTTP readiness and observed idle metadata; it does not prove
app permissions or exclusive ownership. App operations require a dedicated idle
endpoint because WDA session creation replaces its active session. External clients,
URL aliases and a status-to-create race are not atomically excluded. Do not retry
unknown session creation blindly. Launch before capture keeps this app workflow on
its owned ID; capture-before-app continuity/recovery still needs native H3 evidence.

## GUI, scripts and limits

Mobile devices → Actions → Open device owner creates a passive logical owner.
Inspect dependencies does no I/O; Check connection / authorization is explicit.
Edit the operation options JSON and choose Run selected operation, or provide a
flat list of known mobile AC commands and choose Run mobile actions. All batch
names/schemas are validated before input. Desktop, flow/macro/file and nested
commands use the general executor outside this panel. Close device owner rejects
new/late operations immediately; cleanup runs off Qt and failed cleanup can be
retried. Errors stay visible in the result view.

`AC_mobile_surfaces` / `ac_mobile_surfaces` returns the common 13-operation catalog
and every executor command with scope/reason/alternative. Platform aliases use
the same catalog enums in MCP and Builder. Optional adapter absence returns a
dependency/recovery reason rather than inventing native iOS ADB support.
