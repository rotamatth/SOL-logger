/* Keep the top-level document alive: normal page loads would exit fullscreen.
 * The inner app keeps its own routes, Back guard and single active logger.
 */
(() => {
    const start = document.querySelector(".welcome-start-btn");
    let fullscreenDocument = document;
    try {
        // Restore the persistent host, not the child page replaced by navigation.
        if (window.top.document.getElementById("student-session-frame")) {
            fullscreenDocument = window.top.document;
        }
    } catch (_) {
        // A separately embedded preview cannot access its parent document.
    }
    let requesting = null;

    function requestFullscreen() {
        if (fullscreenDocument.fullscreenElement) return Promise.resolve();
        if (requesting) return requesting;
        const root = fullscreenDocument.documentElement;
        if (!root.requestFullscreen || fullscreenDocument.fullscreenEnabled === false) return null;
        const enterFullscreen = async () => {
            // Async functions start synchronously: invoke the API in the trusted
            // input event, and convert synchronous throws into rejected promises.
            await root.requestFullscreen();
        };
        requesting = enterFullscreen().finally(() => { requesting = null; });
        return requesting;
    }

    function retryFullscreen(event) {
        if (!event.isTrusted || event.key === "Escape" || event.ctrlKey || event.metaKey || event.altKey) return;
        // The welcome link below owns the first entry and creates the host.
        if (start && window.top === window.self && start.contains(event.target)) return;
        if (fullscreenDocument.fullscreenElement) return;
        // Failure must never consume the control's action or disable later retries.
        requestFullscreen()?.catch(() => {});
    }

    const inputOptions = { capture: true, passive: true };
    document.addEventListener("pointerup", retryFullscreen, inputOptions);
    document.addEventListener("click", retryFullscreen, inputOptions);
    document.addEventListener("keydown", retryFullscreen, inputOptions);
    if (!window.PointerEvent) document.addEventListener("touchend", retryFullscreen, inputOptions);

    if (!start) return;

    if (window.top !== window.self) {
        // A reset or the ID page's Back link may return here inside the host.
        const guard = document.createElement("script");
        guard.src = start.dataset.backGuardUrl;
        document.head.append(guard);
        return;
    }

    let entering = false;
    start.addEventListener("click", event => {
        if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey
            || event.shiftKey || event.altKey) return;
        if (entering) {
            event.preventDefault();
            return;
        }

        // Older prefixed APIs cannot report completion with a promise.
        // Those browsers use the ordinary link instead of a speculative host.
        const requested = requestFullscreen();
        if (!requested) return;

        event.preventDefault();
        entering = true;
        const fallback = () => window.location.assign(start.href);
        requested.then(() => {
            // A reset link must not clear the new child's session on reload.
            window.history.replaceState(window.history.state, "", start.dataset.fullscreenHostUrl);
            const frame = document.createElement("iframe");
            frame.id = "student-session-frame";
            frame.title = "Percorso di ricerca";
            frame.src = start.href;
            frame.allow = "fullscreen";
            document.body.classList.add("fullscreen-session");
            document.body.replaceChildren(frame);
            frame.focus();
        }).catch(fallback);
    });
})();
