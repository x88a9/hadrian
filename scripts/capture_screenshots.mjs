/**
 * Capture the UI screenshots used in the README.
 *
 * The point of committing this is that the screenshots can be regenerated
 * instead of quietly going stale as the interface changes.
 *
 * It never touches a real database. Expected setup:
 *
 *   1. A throwaway database containing nothing but the synthetic sample
 *      workbook (samples/), imported via POST /import/xlsx.
 *   2. The backend running against it.
 *   3. The frontend built and served on port 3000 — the backend's CORS policy
 *      allows that port only, and a dev server is not used because its HMR
 *      socket can leave the page unhydrated.
 *
 * Every image gets a "SYNTHETIC DATA" badge painted into the page before the
 * shot is taken, so the label survives the image being viewed outside this
 * repository.
 *
 * Usage:
 *   node scripts/capture_screenshots.mjs [--base http://127.0.0.1:3000] [--out docs/img]
 */

import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const args = process.argv.slice(2);
const argOf = (name, fallback) => {
  const i = args.indexOf(name);
  return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
};

const BASE = argOf("--base", "http://127.0.0.1:3000").replace(/\/$/, "");
const OUT = argOf("--out", "docs/img");

const VIEWPORT = { width: 1440, height: 900 };
const SCALE = 2;

/** Painted into every page before capture. */
const BADGE_CSS = `
  #synthetic-data-badge {
    position: fixed;
    right: 14px;
    bottom: 14px;
    z-index: 2147483647;
    padding: 7px 13px;
    border-radius: 7px;
    border: 1px solid rgba(255,255,255,0.22);
    background: rgba(10,10,12,0.86);
    color: #e9e9ea;
    font: 600 12px/1 ui-sans-serif, system-ui, -apple-system, sans-serif;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    pointer-events: none;
  }
`;

const SHOTS = [
  {
    name: "ui-systems-table.png",
    path: "/systems",
    waitFor: "table tbody tr",
    description: "System comparison table with A-F grades",
  },
  {
    name: "ui-system-detail.png",
    path: "/systems/2",
    waitFor: "svg",
    description: "Metrics computed three ways: all, in-sample, out-of-sample",
    // The metric block sits below the rules and the live section.
    prepare: (page) => anchorAt(page, "Backtest-Daten", 24),
  },
  {
    name: "ui-walkforward.png",
    path: "/systems/2",
    waitFor: "svg",
    description: "Walk-forward panel: window schedule and share of positive OOS windows",
    prepare: async (page) => {
      await clickByText(page, "Walk-Forward", ["button", "[role=tab]"]);
      await page.waitForTimeout(900);
      await anchorAt(page, "Quant-Analytik", 24);
    },
  },
  {
    name: "ui-live-ticket.png",
    path: "/live/1",
    waitFor: "body",
    description: "Live ticket detail: six-stage lifecycle and execution quality",
  },
];

async function clickByText(page, text, selectors) {
  for (const sel of selectors) {
    const el = page.locator(`${sel}:has-text("${text}")`).first();
    if (await el.count()) {
      try {
        await el.click({ timeout: 4000 });
        return true;
      } catch {
        /* keep trying the next selector */
      }
    }
  }
  return false;
}

/**
 * Scroll so the section heading `text` sits `offset` px below the viewport top.
 *
 * Anchoring on a heading rather than a pixel offset keeps the framing correct
 * when the page above it grows or shrinks.
 */
async function anchorAt(page, text, offset = 24) {
  const y = await page.evaluate((needle) => {
    const el = Array.from(document.querySelectorAll("h1,h2,h3,div,span")).find(
      (e) => e.textContent?.trim().toLowerCase() === needle.toLowerCase(),
    );
    return el ? el.getBoundingClientRect().top + window.scrollY : null;
  }, text);

  if (y === null) throw new Error(`section heading not found: ${text}`);
  await page.evaluate((top) => window.scrollTo(0, top), Math.max(0, y - offset));
  await page.waitForTimeout(700);
}

async function main() {
  await mkdir(OUT, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    colorScheme: "dark",
    reducedMotion: "reduce",
  });

  const failures = [];

  for (const shot of SHOTS) {
    const url = `${BASE}${shot.path}`;
    const page = await context.newPage();
    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
      await page.waitForSelector(shot.waitFor, { timeout: 20000 });
      if (shot.prepare) await shot.prepare(page);

      // Let Recharts finish its entry animation.
      await page.waitForTimeout(1400);

      await page.addStyleTag({ content: BADGE_CSS });
      await page.evaluate(() => {
        const b = document.createElement("div");
        b.id = "synthetic-data-badge";
        b.textContent = "Synthetic data";
        document.body.appendChild(b);
      });

      const file = path.join(OUT, shot.name);
      await page.screenshot({ path: file });
      console.log(`  ok   ${shot.name.padEnd(26)} ${shot.description}`);
    } catch (err) {
      failures.push(`${shot.name}: ${err.message.split("\n")[0]}`);
      console.error(`  FAIL ${shot.name.padEnd(26)} ${err.message.split("\n")[0]}`);
    } finally {
      await page.close();
    }
  }

  await browser.close();

  if (failures.length) {
    console.error(`\n${failures.length} screenshot(s) failed.`);
    process.exit(1);
  }
  console.log(`\nWrote ${SHOTS.length} screenshots to ${OUT}/`);
}

main();
