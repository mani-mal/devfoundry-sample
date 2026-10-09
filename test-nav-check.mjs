import puppeteer from 'puppeteer';
import { readFileSync } from 'fs';

const creds = JSON.parse(readFileSync('/tmp/opencode/creds.json', 'utf8'));

const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

page.on('pageerror', err => console.log('PAGE-ERROR:', err.message.substring(0, 150)));
page.on('response', async res => {
  if (res.url().includes('/api/') && res.status() >= 400) console.log('API-ERR:', res.status(), res.url().replace('http://localhost:3001', ''));
});

await page.goto('http://localhost:3001/login', { waitUntil: 'networkidle0', timeout: 30000 });
await page.type('input[type="email"]', creds.email);
await page.type('input[type="password"]', creds.password);
await page.click('button[type="submit"]');
await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 10000 });
console.log('Logged in at:', page.url());

// Test SPA nav clicks: /tasks, /project-config, /appliance-health
for (const [linkText, expectedPath] of [['Tasks', '/tasks'], ['Project Config', '/project-config'], ['Appliance Health', '/appliance-health']]) {
  const clicked = await page.evaluate((text) => {
    const links = Array.from(document.querySelectorAll('nav a'));
    const link = links.find(a => a.innerText.trim() === text);
    if (!link) return 'no-link';
    link.click();
    return 'clicked';
  }, linkText);
  await new Promise(r => setTimeout(r, 1500));
  console.log(`${linkText}: ${clicked}, URL now: ${page.url()}`);
  if (page.url() !== expectedPath.replace('3001', '3001')) {
    console.log('  -> did not reach ' + expectedPath);
  }
}

// Test direct browser navigation to /tasks (like refresh)
console.log('--- direct goto /tasks ---');
await page.goto('http://localhost:3001/tasks', { waitUntil: 'networkidle0', timeout: 30000 });
console.log('Direct goto /tasks result URL:', page.url());
const t = await page.evaluate(() => document.body.innerText.substring(0, 80));
console.log('Text:', t.replace(/\n/g, ' | '));

await browser.close();
