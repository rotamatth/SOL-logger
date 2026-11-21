/*
 * The end page stays until a researcher holds the logo for three seconds; it then opens the welcome page
 * with a fresh session, ready for the next group. The logo fades while held, so the researcher sees it working.
 * A tap or a short press does nothing, so the children stay on this page.
 */
(() => {
    const logo = document.getElementById("finished-logo");
    if (!logo) return;
    const HOLD_MS = 3000;
    let timer = null;

    function cancel() {
        window.clearTimeout(timer);
        timer = null;
        logo.classList.remove("is-holding");
    }

    logo.addEventListener("pointerdown", event => {
        event.preventDefault();
        cancel();
        logo.classList.add("is-holding");
        timer = window.setTimeout(() => window.location.replace(logo.dataset.resetUrl), HOLD_MS);
    });
    for (const type of ["pointerup", "pointerleave", "pointercancel"]) logo.addEventListener(type, cancel);
    logo.addEventListener("contextmenu", event => event.preventDefault());
})();
