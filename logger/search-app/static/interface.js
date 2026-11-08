// Keep existing dialog actions and logging handlers as the source of behavior.
(() => {
    const dialogs = Array.from(document.querySelectorAll('.modal[role="dialog"]'));
    if (!dialogs.length) return;

    let activeDialog = null;
    let opener = null;
    const background = new Map();
    const focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), '
        + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    function focusable(dialog) {
        return Array.from(dialog.querySelectorAll(focusableSelector))
            .filter(element => element.tabIndex >= 0 && element.getClientRects().length);
    }

    function restoreBackground() {
        background.forEach((inert, element) => { element.inert = inert; });
        background.clear();
    }

    function syncDialog() {
        const visible = dialogs.find(dialog => !dialog.hidden && getComputedStyle(dialog).display !== 'none');
        if (visible === activeDialog) return;
        restoreBackground();
        if (visible) {
            if (!activeDialog) opener = document.activeElement;
            activeDialog = visible;
            // Help is nested inside <main>; inert only siblings along its path.
            let branch = visible;
            while (branch.parentElement) {
                for (const sibling of branch.parentElement.children) {
                    if (sibling === branch || /^(SCRIPT|STYLE|LINK)$/.test(sibling.tagName)) continue;
                    background.set(sibling, sibling.inert);
                    sibling.inert = true;
                }
                branch = branch.parentElement;
                if (branch === document.body) break;
            }
            document.body.classList.add('dialog-open');
            const initial = visible.querySelector('[data-dialog-initial-focus], textarea') || focusable(visible)[0];
            initial?.focus({preventScroll: true});
        } else {
            activeDialog = null;
            document.body.classList.remove('dialog-open');
            if (opener?.isConnected && !opener.disabled) opener.focus({preventScroll: true});
            opener = null;
        }
    }

    document.addEventListener('keydown', event => {
        if (!activeDialog) return;
        if (event.key === 'Escape') {
            const close = activeDialog.querySelector('button.close:not([disabled])');
            if (close && !window.taskEndLockout) {
                event.preventDefault();
                close.click();
            }
        } else if (event.key === 'Tab') {
            const elements = focusable(activeDialog);
            const first = elements[0];
            const last = elements[elements.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        }
    });

    const observer = new MutationObserver(syncDialog);
    dialogs.forEach(dialog => observer.observe(dialog, {attributes: true, attributeFilter: ['style', 'hidden']}));
    window.addEventListener('pageshow', syncDialog);
    syncDialog();
})();
