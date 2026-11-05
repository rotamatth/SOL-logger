window.addEventListener("pagehide", event => {
    if (event.persisted) document.querySelector(".study-review").hidden = true;
});

window.addEventListener("pageshow", event => {
    if (event.persisted) window.location.reload();
});
