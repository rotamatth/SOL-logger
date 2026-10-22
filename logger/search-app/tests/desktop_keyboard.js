// Run with Playwright CLI against tests/ui_fixture.py; see docs/desktop_interface.md.
async page => {
    page.setDefaultTimeout(3000);
    const origin = new URL(page.url()).origin;
    const failures = [];
    const passed = [];
    function check(condition, message) {
        if (!condition) throw new Error(message);
    }
    async function scenario(name, run) {
        try {
            await run();
            passed.push(name);
        } catch (error) {
            failures.push(`${name}: ${error.message}`);
        }
    }
    await page.setViewportSize({width: 1366, height: 768});
    await scenario('welcome, ID selection and task entry remain keyboard accessible', async () => {
        await page.goto(`${origin}/welcome`);
        await page.getByRole('link', {name: 'Inizia', exact: true}).focus();
        await page.keyboard.press('Enter');
        await page.waitForURL('**/start');
        await page.locator('#id-box').selectOption('UI-TEST');
        await page.locator('#continue-btn').focus();
        await page.keyboard.press('Enter');
        await page.waitForURL('**/task');
        await page.locator('#task-btn').focus();
        await page.keyboard.press('Enter');
        await page.waitForURL(url => url.pathname === '/search');
        const logs = await page.evaluate(() => window.studyLogger.logs);
        check(logs.filter(event => event.type === 'TaskStarted').length === 1, 'task start logging changed');
    });
    await scenario('Escape discards keyboard selection before a typed query is submitted', async () => {
        await page.goto(`${origin}/search`);
        const input = page.getByRole('combobox', {name: 'Cerca', exact: true});
        await input.fill('spa');
        await page.getByRole('listbox').waitFor({state: 'visible'});
        await input.press('ArrowDown');
        const activeId = await input.getAttribute('aria-activedescendant');
        check(activeId, 'combobox does not identify its active option');
        await input.press('Escape');
        check(await input.getAttribute('aria-expanded') === 'false', 'Escape did not close suggestions');
        check(await input.getAttribute('aria-activedescendant') === null, 'Escape left a stale active option');
        await input.press('Enter');
        await page.waitForURL('**/result');
        check(await page.locator('#search-box').inputValue() === 'spa', 'Enter submitted a dismissed suggestion');
    });
    await scenario('ArrowUp selects the last option and Enter searches it exactly once', async () => {
        await page.goto(`${origin}/search`);
        const input = page.getByRole('combobox', {name: 'Cerca', exact: true});
        await input.fill('spa');
        await page.getByRole('listbox').waitFor({state: 'visible'});
        await input.press('ArrowUp');
        check(await page.locator('[aria-selected="true"]').textContent() === 'spazio e pianeti',
              'initial ArrowUp did not select the last suggestion');
        await input.press('Enter');
        await page.waitForURL('**/result');
        const logs = await page.evaluate(() => window.studyLogger.logs);
        const submitted = logs.filter(event => event.type === 'querySubmitted' && event.query === 'spazio e pianeti');
        check(submitted.length === 1, 'selected query was not logged exactly once');
    });
    await scenario('answer and confirmation dialogs keep focus, restore drafts and preserve logging', async () => {
        await page.goto(`${origin}/result?query=spazio`);
        await page.evaluate(() => { window.studyLogger.logs = []; localStorage.setItem('sessionLogs', '[]'); });
        const opener = page.locator('#end-task-btn');
        await opener.click();
        const answer = page.getByRole('dialog', {name: 'Hai completato la risposta?'});
        await answer.waitFor({state: 'visible'});
        const textarea = page.locator('#textarea_feedback');
        await textarea.fill('');
        await page.locator('#feedback-btn').click();
        check(await textarea.getAttribute('aria-invalid') === 'true', 'empty answer did not expose validation');
        check(await answer.isVisible(), 'empty answer bypassed the answer dialog');
        await textarea.fill('Una stella molto grande può formare un buco nero.');
        const close = answer.getByRole('button', {name: 'Chiudi', exact: true});
        await close.focus();
        await page.keyboard.press('Shift+Tab');
        check(await page.evaluate(() => document.activeElement.id) === 'continue-search-btn', 'Shift+Tab escaped the dialog');
        await page.keyboard.press('Tab');
        check(await close.evaluate(element => element === document.activeElement), 'Tab escaped the dialog');
        await page.keyboard.press('Escape');
        await answer.waitFor({state: 'hidden'});
        check(await opener.evaluate(element => element === document.activeElement), 'focus did not return to the opener');
        await opener.click();
        check(await textarea.inputValue() === 'Una stella molto grande può formare un buco nero.', 'draft was lost');
        await page.locator('#feedback-btn').click();
        const confirmation = page.getByRole('dialog', {name: 'Sei sicuro di voler terminare il compito?'});
        await confirmation.waitFor({state: 'visible'});
        check(await page.evaluate(() => document.activeElement.id) === 'no-end-btn', 'confirmation did not focus the safe action');
        await page.locator('#no-end-btn').click();
        await answer.waitFor({state: 'visible'});
        check(await textarea.inputValue() === 'Una stella molto grande può formare un buco nero.', 'returning from confirmation lost the draft');
        await page.locator('#feedback-btn').click();
        const sent = page.waitForRequest(request => request.url().endsWith('/log_session') && request.method() === 'POST');
        await page.locator('#yes-end-btn').click();
        const logs = (await sent).postDataJSON().logs;
        const ended = logs.filter(event => event.type === 'TaskEnded');
        check(ended.length === 1 && ended[0].answer === 'Una stella molto grande può formare un buco nero.', 'final answer logging changed');
        check(logs.some(event => event.type === 'AnswerBoxClosed' && event.reason === 'x-button'), 'Escape lost the existing close event');
        check(logs.filter(event => event.type === 'TaskContinued').length === 1, 'continue event was lost or duplicated');
        await page.waitForURL('**/reward');
    });
    await scenario('question help can be opened and closed from the keyboard', async () => {
        await page.goto(`${origin}/search`);
        const opener = page.locator('#task-help-btn');
        await opener.focus();
        await page.keyboard.press('Enter');
        const dialog = page.getByRole('dialog');
        await dialog.waitFor({state: 'visible'});
        await page.keyboard.press('Escape');
        await dialog.waitFor({state: 'hidden'});
        check(await opener.evaluate(element => element === document.activeElement), 'help did not restore focus');
        const logs = await page.evaluate(() => window.studyLogger.logs);
        check(logs.some(event => event.type === 'taskQuestionHelpClosed'), 'help close event was lost');
    });
    await scenario('viewer back navigation keeps its close and navigation events', async () => {
        await page.goto(`${origin}/webpage`);
        await page.locator('#viewer-back-btn').focus();
        await page.keyboard.press('Enter');
        await page.waitForURL('**/result?*');
        const logs = await page.evaluate(() => window.studyLogger.logs);
        check(logs.some(event => event.type === 'webpageClosed' && event.exitReason === 'back-button'), 'viewer close event was lost');
        check(logs.some(event => event.type === 'customBackButtonClicked'), 'viewer navigation event was lost');
    });
    await scenario('the focused confirmation action stays visible on short screens', async () => {
        await page.setViewportSize({width: 640, height: 400});
        await page.goto(`${origin}/result?query=spazio`);
        await page.locator('#end-task-btn').click();
        await page.locator('#textarea_feedback').fill('Risposta di prova.');
        await page.locator('#feedback-btn').click();
        await page.locator('#endTaskModal').waitFor({state: 'visible'});
        const visible = await page.locator('#no-end-btn').evaluate(element => {
            const rect = element.getBoundingClientRect();
            const box = element.closest('.modal-content-box').getBoundingClientRect();
            return rect.top >= box.top && rect.bottom <= box.bottom;
        });
        check(visible, 'focused confirmation action is outside the scrollable dialog');
    });
    if (failures.length) throw new Error(JSON.stringify({passed, failures}, null, 2));
    return {passed};
}
