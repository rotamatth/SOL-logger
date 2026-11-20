/* Keep the top-level document alive: normal page loads would exit fullscreen.
 * The inner app keeps its own routes, Back guard and single active logger.
 */
(() => {
    const start = document.querySelector(".welcome-start-btn");
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

        const root = document.documentElement;
        // Older prefixed APIs cannot report completion with a promise.
        // Those browsers use the ordinary link instead of a speculative host.
        const request = root.requestFullscreen;
        if (!request || document.fullscreenEnabled === false) return;

        event.preventDefault();
        entering = true;
        const fallback = () => window.location.assign(start.href);
        try {
            // Must run directly in the trusted click, before any asynchronous work.
            const requested = request.call(root);
            Promise.resolve(requested).then(() => {
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
        } catch (_) {
            fallback();
        }
    });
})();
