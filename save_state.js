// save_state.js
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true }); // visible so you can log in
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://auth.wati.io/login', { waitUntil: 'networkidle' });

  console.log('==> Playwright opened a browser. Please log in to WATI in that window.');
  console.log('After you are logged in and your inbox is visible, come back here and press Enter to save the session.');

  process.stdin.once('data', async () => {
    await context.storageState({ path: 'storageState.json' });
    console.log('Saved storageState.json');
    await browser.close();
    process.exit(0);
  });
})();

