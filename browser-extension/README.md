# AutoControl Web Recorder (browser extension)

A Manifest V3 extension that captures clicks, typing, navigation and
form submissions in a browser tab and exports them as an AutoControl
JSON action file driveable by ``AC_web_run`` / ``WR_*`` commands.

## Load it as an unpacked extension

1. Open `chrome://extensions` (or `about:debugging` for Firefox).
2. Enable **Developer mode**.
3. Click **Load unpacked** and pick the `browser-extension/` directory.
4. Pin the **AutoControl Recorder** icon to the toolbar.

## Use it

1. Click the icon, hit **Start** on the page you want to record.
2. Drive the page (click, type, submit forms, navigate).
3. Hit **Stop**, then **Download JSON** — that's the action file.

The exported JSON looks like::

    [
      ["AC_web_open", { "url": "https://example.com" }],
      ["AC_web_run", { "action": "WR_left_click",
                        "params": { "element_name": "#login" } }],
      ["AC_web_run", { "action": "WR_send_keys_to_element",
                        "params": { "element_name": "#username",
                                    "keys": "alice" } }]
    ]

Feed it to AutoControl via `ac.execute_action([...])`,
`AC_execute_files`, the REST API, the scheduler, or the chat-ops bot —
every surface that takes JSON actions works.

## Layout

    browser-extension/
    ├── manifest.json        — MV3 manifest
    ├── background.js        — service worker; recording state machine
    ├── content_script.js    — DOM event capture + CSS-selector builder
    ├── popup.html / popup.js — toolbar UI
    └── icons/               — drop your own .pngs here

The `actionFor()` helper in `background.js` is a pure function and
is unit-tested from Python (`test_browser_extension_scaffold.py`).
