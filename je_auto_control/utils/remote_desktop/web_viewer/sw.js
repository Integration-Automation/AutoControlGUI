// Minimal service worker so the PWA installs cleanly.
// Caches the shell on first visit and serves it offline.
const CACHE = "ac-viewer-v8";
const ASSETS = ["./index.html", "./manifest.webmanifest", "./icon.svg",
                "./mic-worklet.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
});

self.addEventListener("fetch", (event) => {
  // Cache the static shell only; signaling requests pass through to network.
  const url = new URL(event.request.url);
  if (url.pathname.endsWith("/sessions") || url.pathname.includes("/sessions/")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request)),
  );
});
