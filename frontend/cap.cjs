const { chromium } = require('playwright');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const URL = 'file://' + path.join(ROOT, 'docs/opendesign/index4.html').replace(/\\/g, '/');
const OUT_PNG = path.join(ROOT, 'docs/opendesign/index4.png');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  const totalHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  console.log('Height:', totalHeight, 'px');
  await page.setViewportSize({ width: 1920, height: Math.max(totalHeight, 1080) });
  await page.waitForTimeout(500);
  await page.screenshot({ path: OUT_PNG, type: 'png', fullPage: true });
  console.log('PNG saved:', OUT_PNG);
  await browser.close();
})();