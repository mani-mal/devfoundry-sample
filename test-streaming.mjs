import puppeteer from 'puppeteer';
import { readFileSync } from 'fs';
const creds = JSON.parse(readFileSync('/tmp/opencode/creds.json', 'utf8'));

const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

let apiCallCount = 0;
page.on('response', async res => {
  if (res.url().includes('/api/')) {
    apiCallCount++;
    console.log('API:', res.status(), res.request().method(), res.url().replace('http://localhost:3001', ''));
  }
});
page.on('pageerror', err => console.log('PAGE-ERROR:', err.message.substring(0, 200)));

// Login
await page.goto('http://localhost:3001/login', { waitUntil: 'networkidle0', timeout: 30000 });
await page.type('input[type="email"]', creds.email);
await page.type('input[type="password"]', creds.password);
await page.click('button[type="submit"]');
await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 10000 });
console.log('=== LOGGED IN, at', page.url(), '===');

// Go to tasks page and watch polling stream
apiCallCount = 0;
await page.goto('http://localhost:3001/tasks', { waitUntil: 'networkidle0', timeout: 30000 });
console.log('=== ON /tasks, watching 35s of polling ===');

const start = apiCallCount;
await new Promise(r => setTimeout(r, 35000));
console.log(`Polling calls in 35s window: ${apiCallCount - start} (expect ~3 at 15s interval)`);

const tasksInfo = await page.evaluate(() => {
  const rows = document.querySelectorAll('tbody tr');
  return { rowCount: rows.length, bodySnippet: document.body.innerText.substring(0, 150) };
});
console.log('Tasks table:', JSON.stringify(tasksInfo));

await page.screenshot({ path: '/tmp/opencode/shots/devfoundry_streaming.png', fullPage: true });
await browser.close();
console.log('=== STREAMING CHECK DONE ===');
