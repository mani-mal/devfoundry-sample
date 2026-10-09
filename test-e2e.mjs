import puppeteer from 'puppeteer';
import { readFileSync } from 'fs';

const creds = JSON.parse(readFileSync('/tmp/opencode/creds.json', 'utf8'));

const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

const errors = [];
const apiCalls = [];
page.on('pageerror', err => errors.push('PAGE-ERROR: ' + err.message.substring(0, 120)));
page.on('response', async res => {
  if (res.url().includes('/api/')) apiCalls.push(res.status() + ' ' + res.request().method() + ' ' + res.url().replace('http://localhost:3001', ''));
});

const results = [];
const log = (name, pass, detail) => {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'} | ${name} | ${detail}`);
};

// 1. Login
await page.goto('http://localhost:3001/login', { waitUntil: 'networkidle0', timeout: 30000 });
await page.type('input[type="email"]', creds.email);
await page.type('input[type="password"]', creds.password);
await page.click('button[type="submit"]');
try {
  await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 10000 });
  log('login', true, page.url());
} catch {
  log('login', false, 'stayed on /login');
}

await new Promise(r => setTimeout(r, 2000));

// 2. Direct URL loads (full page navigation)
for (const path of ['/dashboard', '/tasks', '/project-config', '/appliance-health']) {
  await page.goto('http://localhost:3001' + path, { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 1200));
  const ok = page.url().includes(path);
  const hasContent = await page.evaluate(() => document.getElementById('root')?.children.length > 0);
  const styled = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  log('direct ' + path, ok && hasContent, `url=${page.url().replace('http://localhost:3001','')} root=${hasContent} bg=${styled}`);
}

// 3. SPA nav clicks (the user's failing case)
await page.goto('http://localhost:3001/dashboard', { waitUntil: 'networkidle0', timeout: 30000 });
await new Promise(r => setTimeout(r, 1000));
for (const [text, path] of [['Tasks', '/tasks'], ['Project Config', '/project-config'], ['Appliance Health', '/appliance-health'], ['Dashboard', '/dashboard']]) {
  const urlBefore = page.url();
  await page.evaluate((t) => {
    const link = Array.from(document.querySelectorAll('nav a')).find(a => a.innerText.trim() === t);
    if (link) link.click();
  }, text);
  await new Promise(r => setTimeout(r, 1500));
  const reached = page.url().includes(path);
  const rootAlive = await page.evaluate(() => document.getElementById('root')?.children.length > 0);
  log('click ' + text, reached && rootAlive, `${urlBefore.replace('http://localhost:3001','')} -> ${page.url().replace('http://localhost:3001','')} rootAlive=${rootAlive}`);
}

// 4. Create new task via modal
await page.goto('http://localhost:3001/tasks', { waitUntil: 'networkidle0', timeout: 30000 });
await new Promise(r => setTimeout(r, 1000));
const before = await page.evaluate(() => document.querySelectorAll('tbody tr').length);
await page.evaluate(() => {
  const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('New Task'));
  if (btn) btn.click();
});
await new Promise(r => setTimeout(r, 800));
const modalOpen = await page.evaluate(() => document.body.innerText.includes('Create New Task'));
log('open new-task modal', modalOpen, 'modal=' + modalOpen);

if (modalOpen) {
  await page.type('form textarea', 'Puppeteer test task - verify full app flow');
  await page.type('form input:nth-of-type(1)', 'dev-foundry');
  const inputs = await page.$$('form input');
  if (inputs.length >= 2) {
    await inputs[inputs.length - 2].click({ clickCount: 3 });
    await inputs[inputs.length - 2].type('dev-foundry');
    await inputs[inputs.length - 1].click({ clickCount: 3 });
    await inputs[inputs.length - 1].type('admin');
  }
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim() === 'Create Task');
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 3000));
  const modalClosed = await page.evaluate(() => !document.body.innerText.includes('Create New Task'));
  log('create task', modalClosed, 'modalClosed=' + modalClosed);
}

// 5. Verify new task appears in list + check API totals
await page.goto('http://localhost:3001/tasks', { waitUntil: 'networkidle0', timeout: 30000 });
await new Promise(r => setTimeout(r, 1500));
const after = await page.evaluate(() => document.querySelectorAll('tbody tr').length);
const taskVisible = await page.evaluate(() => document.body.innerText.includes('Puppeteer test task'));
log('new task in list', taskVisible, `rows before=${before} after=${after} visible=${taskVisible}`);

// 6. Task detail page
const detailLink = await page.evaluate(() => {
  const a = Array.from(document.querySelectorAll('tbody a')).find(a => a.innerText.includes('Puppeteer'));
  return a ? a.getAttribute('href') : null;
});
if (detailLink) {
  await page.goto('http://localhost:3001' + detailLink, { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 1200));
  const detailOk = await page.evaluate(() => document.getElementById('root')?.children.length > 0);
  log('task detail ' + detailLink, detailOk, page.url());
} else {
  log('task detail', false, 'link not found');
}

console.log('\n=== API CALLS ===');
apiCalls.forEach(c => console.log(c));
console.log('\n=== JS ERRORS ===');
if (errors.length) errors.forEach(e => console.log(e)); else console.log('none');

console.log('\n=== SUMMARY ===');
const passed = results.filter(r => r.pass).length;
console.log(`${passed}/${results.length} passed`);
await browser.close();
