// Chromium touch emulation; physical iPad/Brave validation remains required.
async page => {
    page.setDefaultTimeout(3000);
    const origin = new URL(page.url()).origin;
    const report = [];
    for (const [width, height] of [[768, 1024], [1024, 768]]) {
        await page.setViewportSize({width, height});
        await page.goto(`${origin}/search`);
        await page.evaluate(() => { window.studyLogger.logs = []; localStorage.setItem('sessionLogs', '[]'); });
        if (!await page.evaluate(() => navigator.maxTouchPoints > 0 && matchMedia('(pointer: coarse)').matches))
            throw new Error('Run with a touch-enabled browser context');
        await page.locator('#task-help-btn').tap();
        await page.getByRole('dialog').waitFor({state: 'visible'});
        await page.locator('#task-help-close-btn').tap();
        await page.getByRole('dialog').waitFor({state: 'hidden'});
        await page.locator('#search-box').tap();
        await page.locator('#search-box').fill('spa');
        await page.getByRole('listbox').waitFor({state: 'visible'});
        await page.getByRole('option', {name: 'spazio e stelle', exact: true}).tap();
        await page.waitForURL('**/result');
        if (await page.locator('#search-box').inputValue() !== 'spazio e stelle')
            throw new Error('Tapping a suggestion did not submit the chosen query');
        const logs = await page.evaluate(() => window.studyLogger.logs);
        if (!logs.some(event => event.type === 'choseAutoCompleteSuggestion') ||
            logs.filter(event => event.type === 'querySubmitted' && event.query === 'spazio e stelle').length !== 1)
            throw new Error('Touch selection logging was lost or duplicated');
        await page.locator('#end-task-btn').tap();
        const dialog = page.getByRole('dialog', {name: 'Hai completato la risposta?'});
        await dialog.waitFor({state: 'visible'});
        await page.locator('#textarea_feedback').fill('Risposta di prova touch.');
        await dialog.getByRole('button', {name: 'Chiudi', exact: true}).tap();
        await dialog.waitFor({state: 'hidden'});
        report.push({width, height, result: 'help, suggestion tap, answer entry and close work'});
    }
    return report;
}
