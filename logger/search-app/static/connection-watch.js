/*
 * Is this tablet still here, and can it reach the server?
 *
 * - Every 15 seconds, while the page is visible, a short signal tells the server which page is open
 *   (/presenza). The live view uses it to show "fuori dalla pagina" and "nessun segnale". The signal is
 *   separate from saving the logs: if it fails, no log is touched.
 * - When the signal fails twice in a row, or the tablet says it is offline, a full-screen notice asks the
 *   group to raise a hand and call an adult. It goes away by itself as soon as the server answers again.
 * - The log records when the page was really left (hidden for more than a moment, so moving to the next
 *   page does not count) and when the connection dropped and came back, through the page's own logger.
 * - A small service worker shows the same notice when a page cannot be loaded at all (sw.js).
 */
(() => {
    if (window.__solConnectionWatch) return;
    window.__solConnectionWatch = true;

    const BEAT_MS = 15000;
    const RETRY_MS = 5000;
    const HIDDEN_AFTER_MS = 1500;
    const FAILURES_BEFORE_NOTICE = 2;
    const page = () => window.location.pathname;
    const log = (type, details) => {
        try { if (window.studyLogger) window.studyLogger.logEvent(type, { page: page(), ...details }); } catch (_) {}
    };

    let failures = 0;
    let lostAt = null;
    let timer = null;
    let hiddenTimer = null;
    let hiddenAt = null;
    let notice = null;

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
        if (document.visibilityState === "visible") timer = window.setTimeout(beat, delay);
    }

    async function beat() {
        let reached = false;
        try {
            const response = await fetch("/presenza", {
                method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
                cache: "no-store", keepalive: true, body: JSON.stringify({ page: page(), visible: true })
            });
            reached = response.ok;
        } catch (_) {
            reached = false;
        }
        if (reached) {
            failures = 0;
            hideNotice();
        } else if (++failures >= FAILURES_BEFORE_NOTICE || navigator.onLine === false) {
            showNotice(navigator.onLine === false ? "offline" : "no-answer");
        }
        schedule(lostAt === null ? BEAT_MS : RETRY_MS);
    }

    function leftPage() {
        hiddenAt = Date.now();
        log("pageHidden", {});
        const body = JSON.stringify({ page: page(), visible: false });
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
        beat();
    });
    window.addEventListener("pageshow", event => { if (event.persisted) beat(); });
    window.addEventListener("offline", () => { failures = FAILURES_BEFORE_NOTICE; showNotice("offline"); schedule(RETRY_MS); });
    window.addEventListener("online", () => beat());

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
