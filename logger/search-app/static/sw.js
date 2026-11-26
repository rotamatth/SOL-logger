/*
 * The children's pages only: when a page cannot be loaded at all (no network, server down), show the
 * "Alza la mano e chiama un adulto" page instead of the browser's own error.
 *
 * Deliberately small: it handles only GET page loads of the children's app, always from the network, and
 * keeps one file in its cache, offline.html. Form submissions (answers, the ID), the logs, every other
 * request and the dashboard never pass through it. To retire it, serve a version that unregisters itself.
 */
const CACHE = "sol-offline-1";
const OFFLINE_PAGE = "/static/offline.html";

self.addEventListener("install", event => {
    event.waitUntil(caches.open(CACHE)
        .then(cache => cache.add(new Request(OFFLINE_PAGE, { cache: "reload" })))
        .then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
    event.waitUntil(caches.keys()
        .then(keys => Promise.all(keys.filter(key => key.startsWith("sol-offline-") && key !== CACHE)
            .map(key => caches.delete(key))))
        .then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
    const request = event.request;
    if (request.mode !== "navigate" || request.method !== "GET") return;
    const url = new URL(request.url);
    if (url.origin !== self.location.origin || url.pathname.startsWith("/dashboard")) return;
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_PAGE).then(page => page || Response.error())));
});
