// Background service worker — owns the recording state machine and
// turns inbound events from the content script into AutoControl JSON
// action entries. Translation lives in ``actionFor`` so it can be
// unit-tested by importing this module from a Node test runner.

const STATE_KEY = "autocontrol.recorder.state";

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
    return { ...DEFAULT_STATE, ...(stored[STATE_KEY] || {}) };
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

if (typeof chrome !== "undefined" && chrome.runtime) {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        // Returning true keeps the response channel open for async work.
        handleMessage(message, sender, sendResponse);
        return true;
    });
}
