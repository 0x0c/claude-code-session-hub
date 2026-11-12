// Regenerate the README screenshots in docs/images/ for both languages.
//
//   node scripts/screenshots.js
//
// For each language, the script seeds a demo store, starts a hub on a free port, opens the
// dashboard in Chromium (Playwright), pushes one live message so that a card glows, and captures
// the feed and the knowledge tab. It needs Node.js with the `playwright` package and Chromium.
const { chromium } = require("playwright");
const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "docs", "images");
const LIVE_SUMMARY = { en: "Adding tests for incremental updates", ja: "差分更新のテストを追加中" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForHub(url) {
  for (let i = 0; i < 50; i++) {
    try { if ((await fetch(url + "/healthz")).ok) return; } catch (_) {}
    await sleep(100);
  }
  throw new Error("the hub did not start: " + url);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const errors = [];
  for (const [lang, port] of [["en", 8791], ["ja", 8792]]) {
    const store = fs.mkdtempSync(path.join(os.tmpdir(), `hub-shots-${lang}-`));
    execFileSync("python3", ["scripts/demo.py", "--store", store, "--lang", lang], { cwd: ROOT, stdio: "ignore" });
    const hub = spawn("python3", ["-m", "session_hub", "--store", store, "serve", "--port", String(port)],
      { cwd: ROOT, stdio: "ignore" });
    const url = `http://127.0.0.1:${port}`;
    try {
      await waitForHub(url);
      const ctx = await browser.newContext({ locale: lang === "ja" ? "ja-JP" : "en-US", colorScheme: "light",
        viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => errors.push(`${lang}: ${e.message}`));
      await page.goto(`${url}/?lang=${lang}`);
      await page.waitForSelector(".conn.live");
      execFileSync("python3", ["-m", "session_hub", "report", "--summary", LIVE_SUMMARY[lang], "--phase", "test"], {
        cwd: ROOT, stdio: "ignore",
        env: { ...process.env, HUB_URL: url, HUB_SESSION_ID: "session_03SearchIdx", HUB_STATE_DIR: store },
      });
      await page.waitForSelector(".card.glow");
      await sleep(900); // let the glow settle so the capture shows it clearly
      await page.screenshot({ path: path.join(OUT, `dashboard-${lang}.png`) });
      await page.click('[data-view="col:knowledge"]');
      await sleep(300);
      await page.screenshot({ path: path.join(OUT, `knowledge-${lang}.png`) });
      await ctx.close();
    } finally {
      hub.kill();
    }
  }
  await browser.close();
  if (errors.length) { console.error(errors.join("\n")); process.exit(1); }
  console.log("wrote", fs.readdirSync(OUT).map((f) => path.join("docs/images", f)).join(", "));
})();
