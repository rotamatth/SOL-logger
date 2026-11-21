/*
 * The practice question's search pages load this file instead of logger.js. It records nothing.
 *
 * 1. A stand-in with the logger's shape, so the shared page scripts run unchanged: every event is dropped,
 *    nothing is written to the browser's storage and nothing is sent. This tablet may still hold an earlier
 *    group's unsent run in its storage, so the stand-in never clears it either.
 * 2. The two pop-ups that logger.js opens on the real pages, without their events: the question ("?") and
 *    "La mia prima risposta". Keep them in step with the same blocks at the end of logger.js.
 */
(() => {
    const noEvents = Object.freeze([]);
    window.studyLogger = {
        practice: true,
        get logs() { return noEvents; },
        historyTracker: [],
        logEvent() {},
        sendLogs() { return Promise.resolve(); },
        clearClientData() {},
    };

    const helpButton = document.getElementById("task-help-btn");
    const helpDialog = document.getElementById("task-help-modal");
    if (helpButton && helpDialog) {
        helpButton.addEventListener("click", () => { helpDialog.style.display = "flex"; });
        document.getElementById("task-help-close-btn")?.addEventListener("click", () => {
            helpDialog.style.display = "none";
        });
    }

    const answerButton = document.getElementById("search-first-answer-btn");
    const answerDialog = document.getElementById("search-first-answer-dialog");
    if (answerButton && answerDialog) {
        answerButton.addEventListener("click", () => {
            if (window.taskEndLockout || answerDialog.open) return;
            answerDialog.showModal();
        });
        document.getElementById("search-first-answer-close").addEventListener("click", () => answerDialog.close());
        answerDialog.addEventListener("close", () => answerButton.focus());
        answerDialog.addEventListener("click", event => {
            const bounds = answerDialog.getBoundingClientRect();
            if (event.target === answerDialog && (event.clientX < bounds.left || event.clientX > bounds.right
                    || event.clientY < bounds.top || event.clientY > bounds.bottom)) {
                answerDialog.close();
            }
        });
    }
})();
