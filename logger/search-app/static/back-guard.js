/*
 * The browser's back button does nothing on the children's pages: a child only moves forward.
 *
 * Every child page loads this script, before logger.js where the page has one. It fills the history with
 * copies of the current page, so going back lands on a copy and nothing changes; each time that happens the
 * copies are added again and, where the page has the logger, the attempt is recorded as `browserBackBlocked`.
 *
 * If the browser still reaches an earlier page (it may skip history entries that were added without a tap),
 * that page sends the child on to the last page this tab reached. A step page (`data-sol-step-page` on its
 * body: introduction, answer form, review, recap) that comes back from the browser's cache at the same
 * address reloads instead, since one address shows several steps (/task shows the introduction, the answer
 * form and the confirmed answer); the server then shows the step the child is really on. The search page
 * and the viewer keep their page and resynchronize, so their results are not logged twice.
 */
(() => {
    const HISTORY_DEPTH = 10;
    const GUARD_STATE_KEY = "__solBrowserBackBlockerGuard";
    const BASE_STATE_KEY = "__solBrowserBackBlockerBase";
    const LAST_ALLOWED_URL_KEY = "solLastAllowedAppUrl";

    window.__SOLBrowserBackRecoveryInProgress = false;
    let armedUrl = null;
    let needsTappedGuard = true;

    function currentUrl() {
        return window.location?.href || window.location?.origin || "";
    }

    function navigationType() {
        const entries = window.performance?.getEntriesByType?.("navigation") || [];
        return entries[0]?.type || "";
    }

    function isSameOrigin(url) {
        if (!url) return false;
        try {
            return new URL(url, currentUrl()).origin === window.location.origin;
        } catch (_) {
            return false;
        }
    }

    function lastAllowedUrl() {
        try {
            return sessionStorage.getItem(LAST_ALLOWED_URL_KEY);
        } catch (_) {
            return null;
        }
    }

    function storeLastAllowedUrl() {
        const url = currentUrl();
        if (!url) return;
        try {
            sessionStorage.setItem(LAST_ALLOWED_URL_KEY, url);
        } catch (_) {}
    }

    function historyState(extraState = {}) {
        const state = window.history?.state;
        const safeState = state && typeof state === "object" && !Array.isArray(state) ? state : {};
        return { ...safeState, ...extraState, solUrl: currentUrl() };
    }

    // Recorded where the page has the logger (search, answers, viewer, recap, start); the introduction and
    // review pages have none, so a blocked attempt there leaves no event.
    function recordBlocked(reason, targetURL = null) {
        if (!window.studyLogger) return;
        const fromURL = currentUrl();
        window.studyLogger.logEvent("browserBackBlocked", {
            url: fromURL,
            pathname: window.location?.pathname || "",
            fromURL,
            toURL: targetURL || fromURL,
            reason,
            targetURL,
            navigationType: navigationType()
        });
    }

    function arm(force = false) {
        if (!window.history?.replaceState || !window.history?.pushState) return;
        const url = currentUrl();
        if (!force && armedUrl === url) return;
        try {
            window.history.replaceState(historyState({ [BASE_STATE_KEY]: true }), "", url);
            for (let index = 0; index < HISTORY_DEPTH; index += 1) {
                window.history.pushState(
                    historyState({ [GUARD_STATE_KEY]: true, browserBackBlockerGuardIndex: index }), "", url);
            }
            armedUrl = url;
        } catch (error) {
            console.warn("Failed to arm browser back blocker:", error);
        }
    }

    // A copy added during the child's own tap is one the browser will not skip.
    function addTappedGuard() {
        if (!needsTappedGuard || !window.history?.pushState) return;
        needsTappedGuard = false;
        try {
            window.history.pushState(historyState({ [GUARD_STATE_KEY]: true, browserBackBlockerTapped: true }), "",
                currentUrl());
        } catch (_) {}
    }

    function recoveryTarget(event = null) {
        if (!event?.persisted && navigationType() !== "back_forward") return null;
        const last = lastAllowedUrl();
        if (last && last !== currentUrl() && isSameOrigin(last)) return last;
        return event?.persisted && document.body?.hasAttribute("data-sol-step-page") ? currentUrl() : null;
    }

    function recover(reason, event = null) {
        const target = recoveryTarget(event);
        if (!target) return false;
        window.__SOLBrowserBackRecoveryInProgress = true;
        recordBlocked(reason, target);
        try {
            if (target === currentUrl()) window.location.reload();
            else window.location.replace(target);
        } catch (error) {
            console.warn("Failed to recover from native browser back:", error);
        }
        return true;
    }

    function install() {
        if (!window.history?.replaceState || !window.history?.pushState) return;

        window.addEventListener("popstate", () => {
            recordBlocked("popstate", currentUrl());
            needsTappedGuard = true;
            arm(true);
            storeLastAllowedUrl();
        });

        window.addEventListener("pageshow", (event) => {
            if (window.__SOLBrowserBackRecoveryInProgress && !event.persisted) return;
            if (recover("pageshow", event)) return;
            window.__SOLBrowserBackRecoveryInProgress = false;
            storeLastAllowedUrl();
            arm();
        }, true);

        for (const type of ["pointerdown", "keydown"]) {
            window.addEventListener(type, addTappedGuard, { capture: true, passive: true });
        }

        if (recover("back-forward-load")) return;
        storeLastAllowedUrl();
        arm();
    }

    // After the page's deferred scripts, so the logger exists when a recovery is recorded, and before the
    // logger's own DOMContentLoaded work, which waits while a recovery is under way.
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, { once: true });
    else install();
})();
