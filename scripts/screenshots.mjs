#!/usr/bin/env node
// Take the screenshots a spec file asks for, with the changed parts highlighted.
//
//   node scripts/screenshots.mjs --spec shots.json --url http://localhost:7800 --out shots/after
//   node scripts/screenshots.mjs --compare shots/before shots/after --out shots/compare
//
// Needs Playwright (`npm i -g playwright` or an existing install; `require("playwright")` must work).
// Spec: { "shots": [ { "name": "board", "width": 1440, "height": 1000, "full": true,
//          "steps": [ {"click": ".row[data-sid='d-csv']"}, {"press": "Escape"}, {"wait": 300},
//                     {"scroll": ".dsec.related"}, {"hover": "..."} ],
//          "highlight": [ {"sel": ".dsec.related", "label": "New: Also touched"} ],
//          "clip": ".drawer" } ] }
// "highlight" draws a box and a numbered label on every element the selector matches (up to 6),
// so a reviewer sees at once what changed. Selectors that match nothing are reported and fail the run.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require("playwright")); }
catch { try { ({ chromium } = require(require.resolve("playwright", { paths: [process.env.NODE_PATH || "", "/usr/lib/node_modules", "/usr/local/lib/node_modules"] }))); }
  catch { console.error("Playwright not found: npm i -g playwright && npx playwright install chromium"); process.exit(2); } }

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf("--" + k); return i >= 0 ? args[i + 1] : d; };
const out = opt("out", "shots");
// --lenient: for the base branch, where new elements don't exist yet: skip steps whose target is
// missing and draw no highlights.
const lenient = args.includes("--lenient");
fs.mkdirSync(out, { recursive: true });

const HIGHLIGHT = (items) => {
  const colors = ["#ff3d8b", "#ffb020", "#36d399", "#4cc9f0"];
  let n = 0;
  const missing = [];
  for (const [i, it] of items.entries()) {
    const els = [...document.querySelectorAll(it.sel)].slice(0, 6);
    if (!els.length) { missing.push(it.sel); continue; }
    const color = it.color || colors[i % colors.length];
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      n++;
      const box = document.createElement("div");
      box.setAttribute("data-shot-overlay", "");
      Object.assign(box.style, { position: "absolute", left: (r.left + scrollX - 4) + "px", top: (r.top + scrollY - 4) + "px",
        width: (r.width + 8) + "px", height: (r.height + 8) + "px", border: "3px solid " + color, borderRadius: "8px",
        boxShadow: "0 0 0 4px " + color + "33", zIndex: 2147483646, pointerEvents: "none" });
      document.body.append(box);
      if (el === els[0] && it.label) {
        const tag = document.createElement("div");
        tag.setAttribute("data-shot-overlay", "");
        tag.textContent = (i + 1) + "  " + it.label;
        const above = r.top + scrollY - 30 > 0;
        Object.assign(tag.style, { position: "absolute", left: (r.left + scrollX - 4) + "px",
          top: (above ? r.top + scrollY - 32 : r.bottom + scrollY + 8) + "px", background: color, color: "#111",
          font: "700 13px/1.2 system-ui, sans-serif", padding: "5px 9px", borderRadius: "6px", zIndex: 2147483647,
          whiteSpace: "nowrap", pointerEvents: "none" });
        document.body.append(tag);
      }
    }
  }
  return { n, missing };
};

async function shoot(browser, url, spec) {
  const failures = [];
  for (const s of spec.shots) {
    const ctx = await browser.newContext({ viewport: { width: s.width || 1440, height: s.height || 1000 }, deviceScaleFactor: s.scale || 2 });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(url + (s.path || "/"));
    await page.waitForTimeout(s.settle || 1500);
    for (const st of s.steps || []) {
      const target = st.click || st.hover || st.scroll;
      if (target && !(await page.locator(target).count())) {
        if (lenient) { console.log(`  ${s.name}: skipped step, no ${target}`); continue; }
        failures.push(`${s.name}: step target not found: ${target}`); continue;
      }
      if (st.click) await page.locator(st.click).first().click();
      if (st.press) await page.keyboard.press(st.press);
      if (st.hover) await page.locator(st.hover).first().hover();
      if (st.scroll) await page.locator(st.scroll).first().scrollIntoViewIfNeeded();
      await page.waitForTimeout(st.wait || 300);
    }
    // Stop animations so before/after images match where nothing changed
    await page.addStyleTag({ content: "*,*::before,*::after{animation-play-state:paused!important;transition:none!important;caret-color:transparent!important}" });
    const hl = await page.evaluate(HIGHLIGHT, lenient ? [] : s.highlight || []);
    if (hl.missing.length && !spec.allowMissing) failures.push(`${s.name}: highlight matched nothing: ${hl.missing.join(", ")}`);
    const file = path.join(out, s.name + ".png");
    const shotOpts = { path: file, fullPage: !!s.full && !s.clip };
    if (s.clip) { const el = page.locator(s.clip).first(); await el.screenshot({ path: file }); }
    else await page.screenshot(shotOpts);
    if (errors.length) failures.push(`${s.name}: page errors: ${errors.join(" | ")}`);
    console.log(`${file}  (${hl.n} highlighted${errors.length ? ", " + errors.length + " page errors" : ""})`);
    await ctx.close();
  }
  return failures;
}

// Side by side: before | after, one image per shot name found in both folders
async function compare(browser, before, after) {
  const names = fs.readdirSync(after).filter((f) => f.endsWith(".png"));
  for (const f of names) {
    const a = path.join(after, f), b = path.join(before, f);
    const img = (p) => "data:image/png;base64," + fs.readFileSync(p).toString("base64");
    const page = await (await browser.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 })).newPage();
    const col = (title, src) => src ? `<figure><figcaption>${title}</figcaption><img src="${src}"></figure>` : `<figure><figcaption>${title}</figcaption><div class="none">not in this version</div></figure>`;
    await page.setContent(`<style>body{margin:0;background:#0b1220;color:#cbd5e1;font:600 18px system-ui;display:flex;gap:16px;padding:16px;align-items:flex-start}
      figure{margin:0;flex:1;min-width:0}figcaption{padding:0 0 8px}img{width:100%;border:1px solid #334155;border-radius:8px}
      .none{padding:40px;border:1px dashed #334155;border-radius:8px;color:#64748b}</style>
      ${col("Before (base branch)", fs.existsSync(b) ? img(b) : null)}${col("After (this PR)", img(a))}`);
    await page.waitForTimeout(200);
    const file = path.join(out, f);
    await page.screenshot({ path: file, fullPage: true });
    console.log(file);
  }
}

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
let failures = [];
if (args.includes("--compare")) {
  const i = args.indexOf("--compare");
  await compare(browser, args[i + 1], args[i + 2]);
} else {
  const spec = JSON.parse(fs.readFileSync(opt("spec"), "utf8"));
  failures = await shoot(browser, opt("url", "http://localhost:7800"), spec);
}
await browser.close();
if (failures.length) { console.error("\n" + failures.join("\n")); process.exit(1); }
