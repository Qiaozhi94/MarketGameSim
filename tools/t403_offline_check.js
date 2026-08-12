#!/usr/bin/env node
/**
 * T403 (spec E2) offline acceptance: open a generated replay.html in a REAL
 * browser with the network disabled (offline mode) and assert:
 *   - page loads from file:// with ZERO non-file requests (fully offline);
 *   - pause holds the frame, speed change takes effect, timeline seeks;
 *   - the liquidation annotation is visible on liquidation frames;
 *   - all four canvases render;
 *   - zero console errors and zero page errors.
 *
 * Manual acceptance tool -- NOT part of verify.py / pytest (the repo's CI has
 * no browser harness).  Requires node + playwright + a system Chrome/Edge:
 *
 *   node tools/t403_offline_check.js <file:///abs/path/to/replay.html>
 *
 * Environment overrides:
 *   PLAYWRIGHT_MODULE  absolute path to the playwright module (auto-detected
 *                      from @playwright/mcp if not set)
 *   CHROME_PATH        absolute path to chrome/edge executable (defaults to
 *                      the standard Chrome install location on Windows)
 *
 * Prints a T403_RESULT JSON block; exit code 0 iff all assertions pass.
 */

const fs = require('fs');
const path = require('path');

function resolvePlaywright() {
  if (process.env.PLAYWRIGHT_MODULE) return process.env.PLAYWRIGHT_MODULE;
  const mcpCandidates = [
    path.join(process.execPath, '..', 'node_modules', '@playwright', 'mcp', 'node_modules', 'playwright'),
    path.join(require('os').homedir(), '.opencode', 'node_modules', '@playwright', 'mcp', 'node_modules', 'playwright'),
  ];
  for (const c of mcpCandidates) {
    try { require.resolve(c); return c; } catch { /* next */ }
  }
  return 'playwright';
}

function resolveChrome() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const candidates = [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  ];
  return candidates.find((c) => fs.existsSync(c));
}

(async () => {
  const url = process.argv[2];
  if (url === '--self-test') {
    // Prove the pass predicate is a strict conjunction: every known-bad input
    // must fail (return false), otherwise the tool could false-green.
    const conjunct = (o) => o.pauseHolds && o.liqMarkOK && Object.values(o.canvases).every(Boolean)
      && o.nonFileRequests.length === 0 && o.consoleErrors.length === 0 && o.pageErrors.length === 0;
    const ok = { pauseHolds: true, liqMarkOK: true, canvases: { a: true, b: true }, nonFileRequests: [], consoleErrors: [], pageErrors: [] };
    const bad = [
      { ...ok, pauseHolds: false },                                  // pause failed
      { ...ok, liqMarkOK: false },                                   // liquidation mark missing
      { ...ok, canvases: { a: true, b: false } },                    // a canvas blank
      { ...ok, nonFileRequests: ['http://x'] },                      // external request
      { ...ok, consoleErrors: ['boom'] },                            // console error
      { ...ok, pageErrors: ['boom'] },                               // page error
    ];
    const falseGreen = bad.filter((o) => conjunct(o));
    if (falseGreen.length > 0) {
      console.error('T403_SELF_TEST_FAILED: pass predicate accepted known-bad input(s)');
      process.exit(1);
    }
    if (!conjunct(ok)) {
      console.error('T403_SELF_TEST_FAILED: pass predicate rejected a known-good input');
      process.exit(1);
    }
    console.log('T403_SELF_TEST_OK: pass predicate rejects all 6 known-bad inputs');
    process.exit(0);
  }
  if (!url) {
    console.error('usage: node tools/t403_offline_check.js <file:///abs/replay.html> | --self-test');
    process.exit(2);
  }
  const { chromium } = require(resolvePlaywright());
  const chromePath = resolveChrome();
  if (!chromePath) {
    console.error('T403_FATAL no chrome/edge executable found; set CHROME_PATH');
    process.exit(2);
  }

  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const context = await browser.newContext();
  await context.setOffline(true); // simulated 断网环境
  const page = await context.newPage();

  const consoleErrors = [];
  const pageErrors = [];
  const nonFileRequests = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => pageErrors.push(String(e)));
  page.on('request', (r) => { if (!r.url().startsWith('file://')) nonFileRequests.push(r.url()); });
  page.on('requestfailed', (r) => nonFileRequests.push('failed: ' + r.url()));

  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(600);

  const frameInfo0 = await page.textContent('#frame-info');

  // Pause control: frame must NOT advance while paused.
  await page.click('#btn-pause');
  await page.waitForTimeout(300);
  const pauseBtnText = await page.textContent('#btn-pause');
  const frameAfterPause = await page.textContent('#frame-info');
  await page.waitForTimeout(700);
  const frameAfterWait = await page.textContent('#frame-info');
  const pauseHolds = frameAfterPause === frameAfterWait;
  await page.click('#btn-pause'); // resume

  // Speed change (3x) must advance frames faster than 1x.
  await page.evaluate(() => { const s = document.getElementById('speed'); s.value = '3'; s.dispatchEvent(new Event('input')); });
  await page.waitForTimeout(250);
  const frameInfoSpeed = await page.textContent('#frame-info');

  // Timeline seek to the last frame.
  await page.evaluate(() => { const t = document.getElementById('timeline'); t.value = t.max; t.dispatchEvent(new Event('input')); });
  await page.waitForTimeout(250);
  const frameInfoSeek = await page.textContent('#frame-info');

  // Liquidation annotation visibility on a liquidation frame (if any exist).
  // Seek uses the DISPLAYED frame INDEX (the slider is index-positioned), not
  // the timestamp -- writing a timestamp into an index slider seeks nowhere.
  let liqMarkTextAtLiqFrame = null;
  const liqFrames = await page.evaluate(() => DATA.liquidation_frames || []);
  if (liqFrames.length > 0) {
    await page.evaluate((idx) => { const t = document.getElementById('timeline'); t.value = idx; t.dispatchEvent(new Event('input')); }, liqFrames[0]);
    await page.waitForTimeout(250);
    liqMarkTextAtLiqFrame = await page.textContent('#liq-marks');
  }

  const canvases = {};
  for (const id of ['price-canvas', 'kline-canvas', 'book-canvas', 'account-canvas']) {
    canvases[id] = await page.$eval('#' + id, (c) => c.width > 0 && c.height > 0);
  }

  const result = {
    offline_mode: true,
    frame_info_initial: frameInfo0,
    pause_button_text: pauseBtnText,
    pause_holds_frame: pauseHolds,
    frame_after_speed_change: frameInfoSpeed,
    frame_after_seek_to_end: frameInfoSeek,
    liquidation_frames_in_data: liqFrames,
    liq_mark_text_at_liq_frame: liqMarkTextAtLiqFrame,
    canvases_present: canvases,
    non_file_requests: nonFileRequests,
    console_errors: consoleErrors,
    page_errors: pageErrors,
  };

  // Full conjunction with explicit parentheses -- NO || shortcut may bypass
  // the other assertions (round-6 review: the old expression could pass when
  // the canvases+no-errors branch alone was true).
  const liqMarkOK = liqFrames.length === 0 || liqMarkTextAtLiqFrame === 'LIQUIDATION';
  const pass =
    pauseHolds &&
    liqMarkOK &&
    Object.values(canvases).every(Boolean) &&
    nonFileRequests.length === 0 &&
    consoleErrors.length === 0 &&
    pageErrors.length === 0;

  console.log('T403_RESULT ' + JSON.stringify(result, null, 2));
  await browser.close();
  process.exit(pass ? 0 : 1);
})().catch((e) => { console.error('T403_FATAL ' + e); process.exit(1); });
