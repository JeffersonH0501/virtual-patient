// Visual verification script for the auth views.
// Captures desktop and mobile screenshots and extracts layout metrics
// (bounding boxes) for the key elements so layout claims can be checked objectively.
//
// Usage: node scripts/visual-check/capture.mjs [baseUrl]
// Default baseUrl: http://localhost:5173

import {chromium} from 'playwright';
import {mkdir, writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';

const baseUrl = process.argv[2] ?? 'http://localhost:5173';
const outDir = join(dirname(fileURLToPath(import.meta.url)), 'output');

const viewports = [
  {name: 'desktop', width: 1440, height: 900},
  {name: 'mobile', width: 390, height: 844},
];

const routes = ['/signin', '/signup'];

// Elements whose bounding box we want to inspect, by CSS selector.
const trackedSelectors = {
  card: '.auth-card',
  welcome: '.auth-welcome',
  welcomeMain: '.auth-welcome-main',
  media: '.auth-welcome-media',
  illustration: '.auth-illustration',
  copyright: '.auth-copyright',
  content: '.auth-content',
  formContainer: '.auth-form-container',
  firstInput: '.auth-input-wrapper',
  captcha: '.auth-captcha',
  submit: '.auth-submit',
  forgot: '.auth-forgot',
};

const measure = (selectors) => {
  const round = (value) => Math.round(value * 100) / 100;
  const boxOf = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {
      x: round(rect.x),
      y: round(rect.y),
      width: round(rect.width),
      height: round(rect.height),
      right: round(rect.right),
      bottom: round(rect.bottom),
    };
  };
  const result = {};
  for (const [key, selector] of Object.entries(selectors)) result[key] = boxOf(selector);
  return result;
};

const run = async () => {
  await mkdir(outDir, {recursive: true});
  const browser = await chromium.launch();
  const summary = {};

  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: {width: viewport.width, height: viewport.height},
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();

    for (const route of routes) {
      const label = `${route.replace('/', '')}-${viewport.name}`;
      await page.goto(`${baseUrl}${route}`, {waitUntil: 'networkidle'});
      // Give the reCAPTCHA iframe and the SVG a moment to lay out.
      await page.waitForTimeout(1200);

      const shotPath = join(outDir, `${label}.png`);
      await page.screenshot({path: shotPath, fullPage: false});

      const metrics = await page.evaluate(measure, trackedSelectors).catch(() => null);

      summary[label] = metrics;
    }

    await context.close();
  }

  await browser.close();
  await writeFile(join(outDir, 'metrics.json'), JSON.stringify(summary, null, 2), 'utf8');
  console.log(`Saved screenshots and metrics to ${outDir}`);
};

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
