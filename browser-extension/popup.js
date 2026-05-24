/* eslint-env webextensions, browser */
// Popup UI — talks to the background service worker via runtime
// messages. No DOM crawling here; selectors come from content_script.

function send(command, extra = {}) {
    return new Promise((resolve) => {
        chrome.runtime.sendMessage({ command, ...extra }, (reply) => {
            resolve(reply || {});
        });
    });
}

// eslint-disable-next-line security-node/detect-unhandled-async-errors
async function refresh() {
    const reply = await send("status");
    const state = reply.state || {};
    document.getElementById("state").textContent =
        state.recording ? "recording" : "idle";
    document.getElementById("count").textContent =
        String((state.actions || []).length);
}

// Wrap every async event-handler invocation of refresh() in a logged
// .catch so a thrown promise can't drop silently
// (ESLint security-node/detect-unhandled-async-errors).
function safeRefresh() {
    refresh().catch((error) => {
        console.error("refresh failed:", error);
    });
}

document.getElementById("start").addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({
        active: true, currentWindow: true,
    });
    await send("start", { startUrl: tab?.url });
    safeRefresh();
});

document.getElementById("stop").addEventListener("click", async () => {
    await send("stop");
    safeRefresh();
});

document.getElementById("reset").addEventListener("click", async () => {
    await send("reset");
    safeRefresh();
});

document.getElementById("export").addEventListener("click", async () => {
    const reply = await send("export");
    if (!reply.ok) { return; }
    const blob = new Blob([reply.json || "[]"], {
        type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    chrome.downloads.download({
        url,
        filename: "autocontrol-recording.json",
        saveAs: true,
    });
});

// Kick off the initial refresh — safeRefresh() logs any failure.
safeRefresh();
