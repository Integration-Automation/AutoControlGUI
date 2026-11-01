# Android device-side helper

`AndroidCommandLease` (in `je_auto_control/utils/agent_runtime/android_control.py`) asks for
guarantees that only something running **on the device** can give: after a takeover, an expiry or
a cancellation, an old writer must stop injecting; and every command must be settled by its own
request id, the device's boot and the epoch it ran under, with input released and no remote write
left queued. A host-side lock, an `adb shell` return code or a local process exit proves none of
that. This helper is the device side of that contract.

Status: **stage 2 of 4.** The fence ledger and protocol handler (`core/`, JVM unit tests) and the
instrumentation app (`app/`, built into a debug APK) are built in CI
(`.github/workflows/android-helper.yml`). The host provider and emulator tests follow; nothing here
is wired into the runtime yet, and real-device acceptance stays deferred.

## Protocol (version 1)

The helper runs as an instrumentation (`am instrument -w`) with `UiAutomation` access and listens on
the abstract local socket `je_auto_control_helper`; the host reaches it with
`adb forward tcp:<port> localabstract:je_auto_control_helper`. Requests and replies are one JSON
object per line, at most 64 KiB. Identifiers are 32 lowercase hexadecimal characters.

| Request | Reply | Meaning |
| --- | --- | --- |
| `{"op":"hello"}` | `{"protocol":1,"boot_id":…,"helper_epoch":…,"epoch":…}` | `boot_id` is the kernel's `/proc/sys/kernel/random/boot_id`; `helper_epoch` is chosen when the instrumentation starts. |
| `{"op":"fence","epoch":E}` | `{"epoch":E,"fenced":[ids…],"inflight":id\|null,"queue_empty":bool}` | From now on only commands under `E` run. Queued commands under an older epoch become `fenced`; an injecting one is told to stop between events and to release what it pressed. |
| `{"op":"begin","id":I,"epoch":E,"command":{…}}` | `{"id":I,"accepted":bool,"reason":…}` | Refused when `E` is not the current epoch, `I` was seen before, or the queue is full. |
| `{"op":"settle","id":I}` | `{"id":I,"boot_id":…,"epoch":E,"status":S,"input_released":bool,"queue_empty":bool}` | `S` is `queued`, `injecting`, `completed`, `rejected`, `fenced` or `failed`. Only `completed` with `input_released` certifies an effect. |

A command never runs under an epoch other than the one it was begun with, and a fence is final:
there is no request that moves the epoch back.

## Layout

- `core/` — `FenceLedger`, the pure Kotlin state machine every request goes through, and
  `ProtocolHandler`, which turns one decoded request into one reply and accepts only the closed,
  bounded `tap`, `swipe` and `key` command shapes; no Android dependency, so both are tested on the JVM.
  `queue_empty` is true only when nothing is queued **and** nothing is still injecting.
- `app/` — the instrumentation: `HelperServer` serves the abstract socket to a shell or root peer only
  (an abstract socket has no file permissions, so any app could otherwise connect) and bounds each line;
  `Injector` is the only writer and, between events, releases what it pressed once a fence overtakes it.
- `settings.gradle.kts`, `build.gradle.kts` — Gradle build; CI provides Gradle, the JDK and the
  Android SDK (compileSdk 35, minSdk 26, AGP 8.7.3).
