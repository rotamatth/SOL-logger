// Real-template layout smoke test, including short screens and long dialog labels.
async page => {
    page.setDefaultTimeout(3000);
    const origin = new URL(page.url()).origin;
    const failures = [];
    let checked = 0;
    for (const [width, height] of [[320, 568], [375, 667], [768, 1024], [1024, 768],
                                 [1366, 768], [1920, 1080], [1200, 400]]) {
        await page.setViewportSize({width, height});
        for (const path of ['/welcome', '/start', '/task', '/search', '/result?query=spazio', '/webpage']) {
            await page.goto(origin + path);
            const actualWidth = await page.evaluate(() => document.documentElement.scrollWidth);
            if (actualWidth > width) failures.push(`${width}×${height} ${path}: page width ${actualWidth}`);
            if (path.startsWith('/result')) {
                await page.locator('#end-task-btn').click();
                const box = page.locator('#feedbackModal .modal-content-box');
                const fits = await box.evaluate(element => {
                    const rect = element.getBoundingClientRect();
                    return rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight;
                });
                if (!fits) failures.push(`${width}×${height}: answer dialog extends beyond viewport`);
                const actualWidth = await page.evaluate(() => document.documentElement.scrollWidth);
                if (actualWidth > width) failures.push(`${width}×${height}: dialog controls overflow`);
            }
            checked++;
        }
    }
    if (failures.length) throw new Error(JSON.stringify({checked, failures}, null, 2));
    return {checked, result: 'no horizontal page overflow; answer dialogs fit'};
}
