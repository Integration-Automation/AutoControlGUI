/* eslint-env webextensions, browser */
// Content script — observes DOM events in the current tab and forwards
// them to the background service worker for AutoControl-action
// translation. Selectors are computed locally so the background never
// has to touch the live page.

(function () {
    "use strict";

    /**
     * Build a CSS selector for ``element`` that's stable enough to
     * survive normal page mutations: id > test attribute > unique
     * data-name > nth-of-type fallback.
     */
    function selectorFor(element) {
        if (element?.nodeType !== 1) { return ""; }
        if (element.id) {
            return "#" + cssEscape(element.id);
        }
        const testAttrs = ["data-testid", "data-test", "data-cy", "name"];
        for (const attr of testAttrs) {
            const value = element.getAttribute(attr);
            if (value) {
                return `[${attr}="${cssEscape(value)}"]`;
            }
        }
        return nthOfTypeSelector(element);
    }

    function nthOfTypeSelector(element) {
        const path = [];
        let node = element;
        while (node?.nodeType === 1 && node !== document.documentElement) {
            const tag = node.tagName.toLowerCase();
            const parent = node.parentElement;
            if (!parent) {
                path.unshift(tag);
                break;
            }
            const same = Array.prototype.filter.call(
                parent.children,
                (sibling) => sibling.tagName === node.tagName,
            );
            const index = same.indexOf(node) + 1;
            path.unshift(`${tag}:nth-of-type(${index})`);
            node = parent;
        }
        return path.join(" > ");
    }

    function cssEscape(value) {
        if (typeof globalThis.CSS?.escape === "function") {
            return globalThis.CSS.escape(value);
        }
        // Bare-bones fallback for browsers without CSS.escape. The
        // regex literal matches ``"``, ``\`` or ``]``; ``String.raw``
        // keeps the leading backslash in the replacement intact.
        return String(value).replace(/(["\\\]])/g, String.raw`\$1`);
    }

    function send(event) {
        try {
            chrome.runtime.sendMessage({ command: "event", event });
        } catch {
            // Service worker may have torn down between sends — ignore.
        }
    }

    document.addEventListener("click", (event) => {
        send({
            type: "click",
            selector: selectorFor(event.target),
            url: location.href,
        });
    }, true);

    document.addEventListener("change", (event) => {
        const target = event.target;
        if (!target || !(target instanceof HTMLInputElement
            || target instanceof HTMLTextAreaElement
            || target instanceof HTMLSelectElement)) {
            return;
        }
        send({
            type: "input",
            selector: selectorFor(target),
            value: target.value,
            url: location.href,
        });
    }, true);

    document.addEventListener("submit", (event) => {
        send({
            type: "submit",
            selector: selectorFor(event.target),
            url: location.href,
        });
    }, true);

    globalThis.addEventListener("popstate", () => {
        send({ type: "navigate", url: location.href });
    });

    // Initial navigation event for the first page load while the
    // extension is recording.
    send({ type: "navigate", url: location.href });
})();
