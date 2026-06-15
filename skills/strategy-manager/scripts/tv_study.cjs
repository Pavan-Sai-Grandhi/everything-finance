#!/usr/bin/env node
/* TradingView chart study via an authenticated browser session.
 *
 * Loads a real, logged-in TradingView chart (so indicators can be added without
 * the anonymous "Join for free" wall the unauthenticated session hits) and
 * screenshots 2-3 entry setups for the generate-mode visual study.
 *
 * Auth: the SAME mechanism find-trade documents — TRADINGVIEW_SESSIONID +
 * TRADINGVIEW_SESSIONID_SIGN cookies copied from a browser you're logged into,
 * stored in ~/.claude/.env. This script reads them straight from the env it
 * inherits and injects them as cookies; the VALUES never pass through a tool
 * call or get printed (CLAUDE.md: never echo secrets). Run it as:
 *
 *   set -a; source ~/.claude/.env; set +a
 *   node tv_study.cjs --symbol NTPC --date 2023-06-30 --out artifacts/<date>/tv
 *
 * --check  just verifies the session is logged in (no symbol needed) and exits.
 */
const fs = require("fs");
const path = require("path");

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : def;
}
const CHECK = process.argv.includes("--check");
const SYMBOL = (arg("symbol", "") || "").toUpperCase();
const DATE = arg("date", "");           // optional YYYY-MM-DD to center the view
const OUT = arg("out", "artifacts/tv");
const EXCHANGE = arg("exchange", "NSE");

const SID = process.env.TRADINGVIEW_SESSIONID;
const SIGN = process.env.TRADINGVIEW_SESSIONID_SIGN;
if (!SID || !SIGN) {
  console.error("MISSING_COOKIES: source ~/.claude/.env first "
    + "(TRADINGVIEW_SESSIONID / _SIGN). Copy them from DevTools > Application > "
    + "Cookies > tradingview.com on a browser you're logged into.");
  process.exit(3);
}

// resolve the playwright module from the npx cache (no local install needed)
function loadPlaywright() {
  try { return require("playwright"); } catch (e) {}
  const { execSync } = require("child_process");
  const found = execSync(
    "find " + process.env.HOME + "/.npm/_npx -type d -name playwright "
    + "-path '*node_modules*' 2>/dev/null | head -1").toString().trim();
  if (!found) throw new Error("playwright module not found (run `npx playwright --version` once)");
  return require(found);
}

(async () => {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
  // httpOnly auth cookies — must be set on the context, not via document.cookie
  await context.addCookies([
    { name: "sessionid", value: SID, domain: ".tradingview.com", path: "/", httpOnly: true, secure: true },
    { name: "sessionid_sign", value: SIGN, domain: ".tradingview.com", path: "/", httpOnly: true, secure: true },
  ]);
  const page = await context.newPage();

  // Logged-in check: the account endpoint returns the user's profile JSON when
  // the session cookies are valid, a redirect/anon payload when they're not.
  await page.goto("https://www.tradingview.com/", { waitUntil: "domcontentloaded", timeout: 60000 });
  const loggedIn = await page.evaluate(() => {
    const u = (window.user || (window.initData && window.initData.user) || {});
    const hasMenu = !!document.querySelector('button[aria-label*="user menu" i], .js-header-user-menu-button');
    const hasSignIn = !!Array.from(document.querySelectorAll("button,a"))
      .find(e => /sign in/i.test(e.textContent || ""));
    return { username: u && u.username ? u.username : null, hasMenu, hasSignIn };
  });

  const ok = !!(loggedIn.username || (loggedIn.hasMenu && !loggedIn.hasSignIn));
  console.log(JSON.stringify({ logged_in: ok, signal: loggedIn.username ? "profile" : (loggedIn.hasMenu ? "menu" : "none") }));

  if (CHECK) {
    fs.mkdirSync(OUT, { recursive: true });
    await page.screenshot({ path: path.join(OUT, "tv-login-check.png") });
    await browser.close();
    process.exit(ok ? 0 : 4);
  }

  if (!SYMBOL) { console.error("no --symbol given"); await browser.close(); process.exit(2); }
  fs.mkdirSync(OUT, { recursive: true });
  // Chart page; a logged-in session loads the user's saved default layout (apply
  // EMA20/EMA50/SMA200 once on that layout and every study inherits them).
  const url = `https://www.tradingview.com/chart/?symbol=${EXCHANGE}:${SYMBOL}`;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(6000);  // let the chart canvas render
  const shot = path.join(OUT, `tv-${SYMBOL}${DATE ? "-" + DATE : ""}.png`);
  await page.screenshot({ path: shot });
  console.log(JSON.stringify({ symbol: SYMBOL, screenshot: shot, date: DATE || null }));
  await browser.close();
  process.exit(0);
})().catch(e => { console.error("ERROR:", e.message); process.exit(1); });
