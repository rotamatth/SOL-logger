/*
 * Is this tablet still here, and can it reach the server?
 *
 * - Every 2 seconds, while the page is visible, a short report tells the server which page is open, whether
 *   it is visible, whether full screen is on, and saves this tablet could not confirm (/presenza). The live
 *   view's list and its classroom map use it. It is separate from saving the logs: if it fails, no log is
 *   touched. Changes (the page hidden or shown again, full screen left, a save refused) are sent at once.
 * - When the server has not answered for 10 seconds, or the tablet says it is offline, a full-screen notice
 *   asks the group to raise a hand and call an adult. It goes away by itself as soon as the server answers.
 * - The log records when the page was really left (hidden for more than a moment, so moving to the next
 *   page does not count) and when the connection dropped and came back, through the page's own logger.
 * - A small service worker shows the same notice when a page cannot be loaded at all (sw.js).
 *
 * Inside the full-screen host only the inner page runs this: the host page itself does not load it, so a
 * tablet sends one report at a time. A report says nothing of other apps, answers or searches' words.
 */
(() => {
    if (window.__solConnectionWatch) return;
    window.__solConnectionWatch = true;

    const BEAT_MS = 2000;           // research_dashboard/monitor.py BEAT_SECONDS
    const TIMEOUT_MS = 2000;        // A report that hangs is given up, so the next one can go.
    const NOTICE_AFTER_MS = 10000;  // The children's notice: the server silent this long, or the tablet offline.
    const HIDDEN_AFTER_MS = 1500;
    const SAVE_KEY = "solMonitorSave";
    const LAST_SAVE_KEY = "solMonitorLastSave";
    const ORDER_KEY = "solMonitorOrder";
    const page = () => window.location.pathname;
    const log = (type, details) => {
        try { if (window.studyLogger) window.studyLogger.logEvent(type, { page: page(), ...details }); } catch (_) {}
    };
    const stored = (key) => { try { return JSON.parse(window.sessionStorage.getItem(key) || "null"); } catch (_) { return null; } };
    const store = (key, value) => {
        try {
            if (value === null) window.sessionStorage.removeItem(key);
            else window.sessionStorage.setItem(key, JSON.stringify(value));
        } catch (_) { /* Private mode or full storage: the server's own view remains. */ }
    };

    let lastSuccess = Date.now();
    let failures = 0;
    let lostAt = null;
    let timer = null;
    let hiddenTimer = null;
    let hiddenAt = null;
    let notice = null;
    let inFlight = false;
    let again = false;
    let searchSince = null;

    // The full screen that matters is the host's, when this page lives in its frame.
    const fullscreenDocument = (() => {
        try {
            if (window.top !== window.self && window.top.document.getElementById("student-session-frame")) return window.top.document;
        } catch (_) { /* A page embedded elsewhere reports its own document. */ }
        return document;
    })();

    function fullscreen() {
        const enabled = fullscreenDocument.fullscreenEnabled;
        return {
            capable: enabled === undefined ? null : Boolean(enabled && fullscreenDocument.documentElement.requestFullscreen),
            active: enabled === undefined ? null : Boolean(fullscreenDocument.fullscreenElement)
        };
    }

    // The server keeps the newest report: the order never goes back, across this tab's pages too.
    function nextOrder() {
        const order = Math.max(Date.now(), (Number(stored(ORDER_KEY)) || 0) + 1);
        store(ORDER_KEY, order);
        return order;
    }

    function report(visible) {
        const save = stored(SAVE_KEY);
        const lastSave = stored(LAST_SAVE_KEY);
        return {
            order: nextOrder(), page: page(), visible, fullscreen: fullscreen(),
            searchPendingFor: searchSince === null ? null : (Date.now() - searchSince) / 1000,
            incidents: save ? [{ code: "save_unconfirmed", reason: save.reason, for: (Date.now() - save.since) / 1000 }] : [],
            lastSaveFor: lastSave ? (Date.now() - lastSave) / 1000 : null
        };
    }

    function showNotice(reason) {
        if (lostAt === null) {
            lostAt = Date.now();
            log("connectionLost", { reason });
        }
        if (!notice) {
            notice = document.createElement("div");
            notice.id = "connection-lost-notice";
            notice.setAttribute("role", "alertdialog");
            notice.setAttribute("aria-modal", "true");
            notice.setAttribute("aria-labelledby", "connection-lost-title");
            notice.innerHTML = '<div class="connection-lost-box">'
                + '<p id="connection-lost-title" class="connection-lost-title">Il collegamento non funziona.</p>'
                + '<p class="connection-lost-text">Alza la mano e chiama un adulto.</p>'
                + '<p class="connection-lost-wait">Riprovo da solo…</p></div>';
            document.body.append(notice);
        }
        notice.hidden = false;
    }

    function hideNotice() {
        if (lostAt !== null) {
            log("connectionBack", { lostSeconds: Math.round((Date.now() - lostAt) / 1000) });
            lostAt = null;
        }
        if (notice) notice.hidden = true;
    }

    function schedule(delay) {
        window.clearTimeout(timer);
        if (document.visibilityState === "visible") timer = window.setTimeout(beat, Math.max(0, delay));
    }

    // One report at a time; a change during one is sent right after it. Never rejects.
    async function beat() {
        if (inFlight) { again = true; return; }
        inFlight = true;
        again = false;
        const started = Date.now();
        const controller = window.AbortController ? new AbortController() : null;
        const abort = window.setTimeout(() => { if (controller) controller.abort(); }, TIMEOUT_MS);
        let reached = false;
        try {
            const response = await fetch("/presenza", {
                method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
                cache: "no-store", keepalive: true, body: JSON.stringify(report(true)),
                signal: controller ? controller.signal : undefined
            });
            reached = response.ok;
        } catch (_) {
            reached = false;
        } finally {
            window.clearTimeout(abort);
            inFlight = false;
        }
        if (reached) {
            failures = 0;
            lastSuccess = Date.now();
            hideNotice();
        } else {
            failures += 1;
            if (navigator.onLine === false) showNotice("offline");
            else if (failures >= 2 && Date.now() - lastSuccess >= NOTICE_AFTER_MS) showNotice("no-answer");
        }
        // The next report is due two seconds after this one started, not after it ended.
        schedule(again ? 0 : BEAT_MS - (Date.now() - started));
    }

    function leftPage() {
        hiddenAt = Date.now();
        log("pageHidden", {});
        const body = JSON.stringify(report(false));
        try {
            if (!navigator.sendBeacon || !navigator.sendBeacon("/presenza", new Blob([body], { type: "application/json" }))) {
                fetch("/presenza", { method: "POST", headers: { "Content-Type": "application/json" },
                                     credentials: "same-origin", keepalive: true, body }).catch(() => {});
            }
        } catch (_) {}
    }

    document.addEventListener("visibilitychange", () => {
        window.clearTimeout(hiddenTimer);
        if (document.visibilityState === "hidden") {
            window.clearTimeout(timer);
            // Moving to the next page also hides this one for an instant: only a page still open counts.
            hiddenTimer = window.setTimeout(leftPage, HIDDEN_AFTER_MS);
            return;
        }
        if (hiddenAt !== null) {
            log("pageVisible", { hiddenSeconds: Math.round((Date.now() - hiddenAt) / 1000) });
            hiddenAt = null;
        }
        void beat();
    });
    fullscreenDocument.addEventListener("fullscreenchange", () => { void beat(); });
    // A search that has not come back yet: the old page keeps reporting while the next one loads.
    document.addEventListener("submit", event => {
        const action = event.target && event.target.getAttribute ? event.target.getAttribute("action") || "" : "";
        if (/\/(prova\/)?risultati|\/result/.test(action) || event.target.querySelector("#search-box")) searchSince = Date.now();
    }, true);
    // The children's scripts say when a save is confirmed or not (first-answer.js, final-answer-draft.js, recap.js).
    window.addEventListener("sol:save", event => {
        const detail = event.detail || {};
        if (detail.ok) {
            store(SAVE_KEY, null);
            store(LAST_SAVE_KEY, Date.now());
        } else if (!stored(SAVE_KEY)) {
            store(SAVE_KEY, { reason: detail.reason || "unconfirmed", since: Date.now() });
        }
        void beat();
    });
    window.addEventListener("pageshow", event => { if (event.persisted) void beat(); });
    window.addEventListener("offline", () => { showNotice("offline"); schedule(BEAT_MS); });
    window.addEventListener("online", () => { void beat(); });

    const style = document.createElement("style");
    style.textContent = "#connection-lost-notice{position:fixed;inset:0;z-index:2147483646;display:flex;"
        + "align-items:center;justify-content:center;padding:24px;background:rgb(32 45 72 / 82%)}"
        + "#connection-lost-notice[hidden]{display:none}"
        + ".connection-lost-box{max-width:520px;padding:32px 28px;border-radius:24px;background:#fff;text-align:center;"
        + "font-family:inherit;box-shadow:0 10px 40px rgb(0 0 0 / 30%)}"
        + ".connection-lost-title{margin:0 0 10px;color:#c5221f;font-size:1.6rem;font-weight:800}"
        + ".connection-lost-text{margin:0 0 14px;color:#111;font-size:1.35rem;font-weight:700}"
        + ".connection-lost-wait{margin:0;color:#5f6368;font-size:1rem}";
    document.head.append(style);

    if ("serviceWorker" in navigator && window.isSecureContext) {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    }
    schedule(document.visibilityState === "visible" ? 0 : BEAT_MS);
})();
