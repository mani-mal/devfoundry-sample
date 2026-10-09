import puppeteer from 'puppeteer';
import { readFileSync } from 'fs';

const creds = JSON.parse(readFileSync('/tmp/opencode/creds.json', 'utf8'));

const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

const failed = [];
page.on('response', async res => {
  if (res.url().includes('/api/')) console.log('API:', res.status(), res.request().method(), res.url().replace('http://localhost:3001', ''));
});
page.on('pageerror', err => console.log('PAGE-ERROR:', err.message.substring(0, 200)));

await page.goto('http://localhost:3001/login', { waitUntil: 'networkidle0', timeout: 30000 });

const cssCheck = await page.evaluate(() => {
  const sheets = Array.from(document.styleSheets);
  let rules = 0;
  try { rules = sheets.reduce((n, s) => n + (s.cssRules ? s.cssRules.length : 0), 0); } catch {}
  const body = getComputedStyle(document.body);
  const root = document.getElementById('root');
  return {
    styleSheetCount: sheets.length,
    cssRuleCount: rules,
    bodyBg: body.backgroundColor,
    bodyFont: body.fontFamily.substring(0, 40),
    rootHasChildren: !!(root && root.children.length),
  };
});
console.log('CSS CHECK:', JSON.stringify(cssCheck, null, 2));

await page.screenshot({ path: '/tmp/opencode/shots/login_styled.png', fullPage: true });

await page.type('input[type="email"]', creds.email);
await page.type('input[type="password"]', creds.password);
await page.click('button[type="submit"]');
try {
  await page.waitForFunction(() => !window.location.pathname.includes('/login'), { timeout: 10000 });
  console.log('LOGIN SUCCESS ->', page.url());
  await new Promise(r => setTimeout(r, 2500));
  const dashCheck = await page.evaluate(() => {
    const body = getComputedStyle(document.body);
    const nav = document.querySelector('nav');
    return {
      bodyBg: body.backgroundColor,
      hasNav: !!nav,
      navBg: nav ? getComputedStyle(nav).backgroundColor : null,
      textSnippet: document.body.innerText.substring(0, 120),
    };
  });
  console.log('DASHBOARD:', JSON.stringify(dashCheck, null, 2));
  await page.screenshot({ path: '/tmp/opencode/shots/dashboard_styled.png', fullPage: true });
} catch {
  console.log('LOGIN FAILED, still at', page.url());
  console.log(await page.evaluate(() => document.body.innerText.substring(0, 200)));
}

await browser.close();
