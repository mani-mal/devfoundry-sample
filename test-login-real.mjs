import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

page.on('response', async res => {
  if (res.url().includes('/api/')) {
    console.log('API:', res.status(), res.request().method(), res.url().replace('http://localhost:3001', ''));
  }
});
page.on('pageerror', err => console.log('PAGE-ERROR:', err.message.substring(0, 200)));

await page.goto('http://localhost:3001/login', { waitUntil: 'networkidle0', timeout: 30000 });

await page.type('input[type="email"]', '<EMAIL_ADDRESS_1>');
await page.type('input[type="password"]', 'devfoundry');
await page.click('button[type="submit"]');

try {
  await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 10000 });
  console.log('LOGIN SUCCESS ->', page.url());
} catch {
  console.log('FAILED, still at', page.url());
  console.log(await page.evaluate(() => document.body.innerText.substring(0, 200)));
}

await page.screenshot({ path: '/tmp/opencode/shots/devfoundry_login_fixed.png', fullPage: true });
await browser.close();
