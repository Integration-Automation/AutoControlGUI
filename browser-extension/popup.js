// Popup UI — talks to the background service worker via runtime
// messages. No DOM crawling here; selectors come from content_script.

function send(command, extra = {}) {
    return new Promise((resolve) => {
        chrome.runtime.sendMessage({ command, ...extra }, (reply) => {
            resolve(reply || {});
        });
    });
}

async function refresh() {
    const reply = await send("status");
    const state = reply.state || {};
    document.getElementById("state").textContent =
        state.recording ? "recording" : "idle";
    document.getElementById("count").textContent =
        String((state.actions || []).length);
}

document.getElementById("start").addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({
        active: true, currentWindow: true,
    });
    await send("start", { startUrl: tab?.url });
    refresh();
});

document.getElementById("stop").addEventListener("click", async () => {
    await send("stop");
    refresh();
});

document.getElementById("reset").addEventListener("click", async () => {
    await send("reset");
    refresh();
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

// Popup HTML loads this script as a classic script (not a module), so
// top-level ``await`` isn't legal. The async IIFE below is the
// equivalent — Sonar's S7785 accepts it because the promise is
// explicitly awaited inside the wrapper.
(async () => {
    await refresh();
})();
