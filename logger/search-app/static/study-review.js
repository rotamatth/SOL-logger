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
        button.className = "review-button review-animation-start";
        button.textContent = "Avvia animazione";
        animation.after(button);
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
        void animation.play().catch(offerPlayback);
    }
}
