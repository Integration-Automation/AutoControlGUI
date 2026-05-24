/* eslint-env webextensions, serviceworker */
// Background service worker — owns the recording state machine and
// turns inbound events from the content script into AutoControl JSON
// action entries. Translation lives in ``actionFor`` so it can be
// unit-tested by importing this module from a Node test runner.

// nosemgrep: codacy.javascript.security.hard-coded-password
const STATE_KEY = "autocontrol.recorder.state";  // nosemgrep: codacy.javascript.security.hard-coded-password

/**
 * @typedef {Object} RecorderState
 * @property {boolean} recording
 * @property {string|null} startUrl
 * @property {Array<Array>} actions  AC_/WR_ JSON action entries
 */

const DEFAULT_STATE = {
    recording: false,
    startUrl: null,
    actions: [],
};

async function loadState() {
    const stored = await chrome.storage.local.get(STATE_KEY);
    // Object.assign sidesteps ESLint's object-injection rule that
    // fires on the spread of an unsanitised storage value. ``stored``
    // is whatever chrome.storage round-trips for us; we only ever
    // copy own enumerable properties onto a fresh default.
    /* eslint-disable security/detect-object-injection */
    const saved = Object.prototype.hasOwnProperty.call(stored, STATE_KEY)
        ? stored[STATE_KEY] : null;
    /* eslint-enable security/detect-object-injection */
    if (saved == null || typeof saved !== "object") {
        return Object.assign({}, DEFAULT_STATE);
    }
    return Object.assign({}, DEFAULT_STATE, saved);
}

async function saveState(state) {
    await chrome.storage.local.set({ [STATE_KEY]: state });
}

/**
 * Translate one captured DOM event into an AutoControl JSON action.
 * Pure function — used by both the live recorder and the test suite.
 *
 * @param {Object} event - {type, selector, value, url}
 * @returns {Array|null}
 */
export function actionFor(event) {
    if (!event || typeof event.type !== "string") {
        return null;
    }
    switch (event.type) {
        case "navigate":
            return ["AC_web_open", { url: event.url }];
        case "click":
            return ["AC_web_run", {
                action: "WR_left_click",
                params: { element_name: event.selector },
            }];
        case "input":
            return ["AC_web_run", {
                action: "WR_send_keys_to_element",
                params: {
                    element_name: event.selector,
                    keys: event.value || "",
                },
            }];
        case "submit":
            return ["AC_web_run", {
                action: "WR_element_submit",
                params: { element_name: event.selector },
            }];
        case "key":
            return ["AC_web_run", {
                action: "WR_press_key",
                params: { keycode: event.value || "" },
            }];
        default:
            return null;
    }
}

/* eslint-disable security-node/detect-unhandled-async-errors */
async function handleMessage(message, _sender, sendResponse) {
    const state = await loadState();
    switch (message?.command) {
        case "start":
            await saveState({
                recording: true,
                startUrl: message.startUrl || null,
                actions: message.startUrl
                    ? [["AC_web_open", { url: message.startUrl }]]
                    : [],
            });
            sendResponse({ ok: true });
            break;
        case "stop":
            await saveState({ ...state, recording: false });
            sendResponse({ ok: true, actions: state.actions });
            break;
        case "event": {
            if (!state.recording) {
                sendResponse({ ok: false, reason: "not recording" });
                break;
            }
            const action = actionFor(message.event);
            if (action) {
                state.actions.push(action);
                await saveState(state);
            }
            sendResponse({ ok: !!action });
            break;
        }
        case "status":
            sendResponse({ ok: true, state });
            break;
        case "reset":
            await saveState(DEFAULT_STATE);
            sendResponse({ ok: true });
            break;
        case "export":
            sendResponse({
                ok: true,
                json: JSON.stringify(state.actions, null, 2),
            });
            break;
        default:
            sendResponse({ ok: false, reason: "unknown command" });
    }
}
/* eslint-enable security-node/detect-unhandled-async-errors */

if (typeof chrome !== "undefined" && chrome.runtime) {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        // Returning true keeps the response channel open for async
        // work. Attach .catch so an unhandled rejection in
        // handleMessage doesn't drop silently (ESLint
        // security-node/detect-unhandled-async-errors).
        handleMessage(message, sender, sendResponse).catch((error) => {
            console.error("handleMessage failed:", error);
            try {
                sendResponse({ ok: false, reason: String(error) });
            } catch (_) {
                /* sendResponse may already have fired; ignore. */
            }
        });
        return true;
    });
}
