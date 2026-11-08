window.addEventListener("pagehide", event => {
    if (event.persisted) document.querySelector(".study-review").hidden = true;
});

window.addEventListener("pageshow", event => {
    if (event.persisted) window.location.reload();
});

const animation = document.querySelector(".review-animation");
if (animation) {
    animation.controls = false;

    function offerPlayback() {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "review-button review-button--outline review-animation-start";
        button.textContent = "Avvia animazione";
        document.querySelector(".review-actions").prepend(button);
        button.addEventListener("click", async () => {
            try {
                await animation.play();
                button.remove();
            } catch {
                // Keep the button available if the browser refuses playback.
            }
        });
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        offerPlayback();
    } else {
        // A clip that cannot load leaves its still on screen, and a button would do nothing.
        void animation.play().catch(() => {
            if (!animation.error) offerPlayback();
        });
    }
}
