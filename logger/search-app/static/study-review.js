window.addEventListener("pagehide", event => {
    if (event.persisted) document.querySelector(".study-review").hidden = true;
});

window.addEventListener("pageshow", event => {
    if (event.persisted) window.location.reload();
});

const animation = document.querySelector(".review-animation");
if (animation && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    void animation.play().catch(() => { /* The playback controls remain available. */ });
}
