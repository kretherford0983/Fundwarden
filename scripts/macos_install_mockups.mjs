// Draws the illustrations used in docs/install-macos.md (issue #61): simplified mock-ups of the macOS windows a user
// sees when installing PennyWarden and allowing it to open the first time. They are drawings, not screenshots, and
// each one is marked "Illustration"; the wording follows macOS 15 (Sequoia) and may differ slightly on other versions.
//
//   node scripts/macos_install_mockups.mjs        (needs `npm --prefix frontend ci`)
//
// Writes docs/screenshots/macos/*.png.
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(join(ROOT, "frontend", "package.json"));
const { chromium } = require("@playwright/test");
const OUT = join(ROOT, "docs", "screenshots", "macos");
mkdirSync(OUT, { recursive: true });
const COIN = readFileSync(join(ROOT, "frontend", "public", "favicon.svg"), "utf8").replace(/role="img"[^>]*>/, ">");
const icon = (size) => `<span class="appicon" style="width:${size}px;height:${size}px">${COIN}</span>`;
const FOLDER = `<svg viewBox="0 0 64 52" width="88" height="72"><path d="M2 8a4 4 0 0 1 4-4h18l5 6h29a4 4 0 0 1 4 4v32a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4z" fill="#3d9be9"/><path d="M2 16h60v30a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4z" fill="#62b4f5"/><path d="M22 38l10-14 10 14z" fill="#e8f4ff" opacity=".9"/><rect x="26" y="36" width="12" height="4" rx="1" fill="#e8f4ff" opacity=".9"/></svg>`;

const CSS = `
* { box-sizing: border-box; }
body { margin: 0; font: 13px -apple-system, "Helvetica Neue", "Segoe UI", Inter, Arial, sans-serif; color: #1d1d1f; }
.desk { position: relative; width: 900px; height: 540px; overflow: hidden;
        background: #aeb8d0; display: flex; align-items: center; justify-content: center; }
.tag { position: absolute; right: 12px; bottom: 10px; background: rgba(0,0,0,.55); color: #fff; font-size: 11px; padding: 3px 8px; border-radius: 4px; letter-spacing: .02em; }
.win { background: #f5f5f7; border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,.35), 0 0 0 .5px rgba(0,0,0,.25); overflow: hidden; }
.bar { height: 38px; display: flex; align-items: center; padding: 0 14px; background: #ececee; border-bottom: 1px solid #d6d6d8; position: relative; }
.lights { display: flex; gap: 8px; } .lights i { width: 12px; height: 12px; border-radius: 50%; display: block; }
.lights i:nth-child(1) { background: #ff5f57; } .lights i:nth-child(2) { background: #febc2e; } .lights i:nth-child(3) { background: #28c840; }
.bar .title { position: absolute; left: 0; right: 0; text-align: center; font-weight: 600; color: #4a4a4c; pointer-events: none; }
.appicon { display: inline-block; } .appicon svg { width: 100%; height: 100%; display: block; }
.alert { width: 300px; background: rgba(246,246,248,.98); border-radius: 14px; padding: 22px 18px 16px; text-align: center;
         box-shadow: 0 24px 60px rgba(0,0,0,.4), 0 0 0 .5px rgba(0,0,0,.2); }
.alert h1 { font-size: 14px; margin: 12px 0 8px; } .alert p { font-size: 11.5px; line-height: 1.4; margin: 0 0 8px; color: #333; }
.btn { display: block; width: 100%; border: 0; border-radius: 7px; padding: 6px 10px; margin-top: 8px; font: inherit; font-size: 13px; background: #e0e0e3; color: #1d1d1f; }
.btn.blue { background: #0a84ff; color: #fff; }
.pill { display: inline-block; border: 0; border-radius: 6px; padding: 4px 12px; font: inherit; background: #fff; box-shadow: 0 0 0 .5px rgba(0,0,0,.25), 0 1px 1px rgba(0,0,0,.1); }
.hl { outline: 3px solid #ff3b30; outline-offset: 3px; border-radius: 8px; position: relative; }
.num { position: absolute; width: 26px; height: 26px; border-radius: 50%; background: #ff3b30; color: #fff; font-weight: 700;
       display: flex; align-items: center; justify-content: center; font-size: 14px; box-shadow: 0 2px 6px rgba(0,0,0,.3); z-index: 3; }
.warnbadge { position: relative; display: inline-block; }
.warnbadge::after { content: "!"; position: absolute; right: -6px; bottom: -4px; width: 24px; height: 22px; background: #ffcc00; color: #1d1d1f;
       font-weight: 800; font-size: 14px; display: flex; align-items: center; justify-content: center; clip-path: polygon(50% 0, 100% 100%, 0 100%); padding-top: 5px; }
`;
const page = (body) => `<!doctype html><html><head><meta charset="utf-8"><style>${CSS}</style></head><body><div class="desk">${body}<span class="tag">Illustration</span></div></body></html>`;

const shots = {
  // 1. The opened disk image: drag the app onto Applications.
  "1-disk-image.png": page(`
    <div class="win" style="width:560px">
      <div class="bar"><div class="lights"><i></i><i></i><i></i></div><div class="title">PennyWarden</div></div>
      <div style="height:300px;background:#fff;display:flex;align-items:center;justify-content:space-around;padding:0 50px;position:relative">
        <div style="text-align:center">${icon(96)}<div style="margin-top:8px">PennyWarden</div></div>
        <svg width="140" height="40" viewBox="0 0 140 40"><path d="M5 20h98" stroke="#ff3b30" stroke-width="5" stroke-linecap="round" stroke-dasharray="1 11"/><path d="M112 6l22 14-22 14z" fill="#ff3b30"/></svg>
        <div style="text-align:center">${FOLDER}<div style="margin-top:8px">Applications</div></div>
        <div style="position:absolute;bottom:22px;left:0;right:0;text-align:center;color:#6e6e73">Drag PennyWarden onto Applications</div>
      </div>
    </div>`),
  // 2. First start: macOS refuses to open the app. Click Done.
  "2-not-opened.png": page(`
    <div class="alert">
      <span class="warnbadge">${icon(64)}</span>
      <h1>“PennyWarden” Not Opened</h1>
      <p>Apple could not verify “PennyWarden” is free of malware that may harm your Mac or compromise your privacy.</p>
      <span class="hl" style="display:block;margin-top:14px"><button class="btn blue" style="margin:0">Done</button><span class="num" style="right:-40px;top:2px">1</span></span>
      <button class="btn">Move to Trash</button>
    </div>`),
  // 3. System Settings → Privacy & Security → Security: Open Anyway.
  "3-privacy-security.png": page(`
    <div class="win" style="width:760px;display:flex;flex-direction:column">
      <div class="bar"><div class="lights"><i></i><i></i><i></i></div><div class="title">Privacy &amp; Security</div></div>
      <div style="display:flex;height:400px">
        <div style="width:200px;background:#e9e9ec;padding:10px 8px;border-right:1px solid #d6d6d8;font-size:12.5px">
          ${["Wi‑Fi", "Bluetooth", "Network", "Notifications", "Sound", "Focus", "General", "Appearance", "Accessibility"].map((x) => `<div style="padding:5px 8px;color:#333">${x}</div>`).join("")}
          <div class="hl" style="padding:5px 8px;background:#0a84ff;color:#fff;border-radius:6px;font-weight:600">Privacy &amp; Security<span class="num" style="right:-38px;top:0">2</span></div>
          ${["Desktop &amp; Dock", "Displays"].map((x) => `<div style="padding:5px 8px;color:#333">${x}</div>`).join("")}
        </div>
        <div style="flex:1;padding:18px 24px;background:#f5f5f7">
          <div style="color:#6e6e73;font-size:12px;margin-bottom:6px">… scroll down to <b>Security</b></div>
          <div style="font-weight:700;font-size:15px;margin:10px 0 8px">Security</div>
          <div style="background:#fff;border-radius:10px;box-shadow:0 0 0 .5px rgba(0,0,0,.15)">
            <div style="padding:12px 14px;border-bottom:1px solid #e5e5ea;display:flex;justify-content:space-between;align-items:center">
              <span>Allow applications from</span><span class="pill">App Store &amp; Known Developers ⌄</span></div>
            <div style="padding:14px;display:flex;justify-content:space-between;align-items:center">
              <span>“PennyWarden” was blocked to protect your Mac.</span>
              <span class="hl"><button class="pill" style="font-weight:600">Open Anyway</button><span class="num" style="right:-40px;top:-1px">3</span></span>
            </div>
          </div>
          <div style="color:#6e6e73;font-size:12px;margin-top:14px">The line and the button appear for about an hour after macOS refused to open the app.</div>
        </div>
      </div>
    </div>`),
  // 4. Confirm: Open Anyway, then your password or Touch ID.
  "4-open-anyway.png": page(`
    <div class="alert">
      <span class="warnbadge">${icon(64)}</span>
      <h1>Open “PennyWarden”?</h1>
      <p>Apple is not able to verify that it is free from malware that could harm your Mac or compromise your privacy. Don’t open this unless you are certain it is from a trustworthy source.</p>
      <span class="hl" style="display:block;margin-top:14px"><button class="btn blue" style="margin:0">Open Anyway</button><span class="num" style="right:-40px;top:2px">4</span></span>
      <button class="btn">Move to Trash</button>
      <button class="btn">Done</button>
    </div>`),
  // macOS 14 and earlier: right-click (Control-click) the app → Open.
  "5-right-click-open.png": page(`
    <div class="win" style="width:560px">
      <div class="bar"><div class="lights"><i></i><i></i><i></i></div><div class="title">Applications</div></div>
      <div style="height:300px;background:#fff;position:relative;padding:40px 60px">
        <div style="display:inline-block;text-align:center">${icon(80)}<div style="margin-top:6px;background:#0a84ff;color:#fff;border-radius:4px;padding:0 6px">PennyWarden</div></div>
        <div style="position:absolute;left:170px;top:70px;width:220px;background:rgba(246,246,248,.98);border-radius:8px;padding:5px;box-shadow:0 10px 30px rgba(0,0,0,.3),0 0 0 .5px rgba(0,0,0,.2)">
          <div class="hl" style="padding:4px 10px;background:#0a84ff;color:#fff;border-radius:4px">Open<span class="num" style="right:-40px;top:-2px">1</span></div>
          ${["Show Package Contents", "—", "Move to Trash", "—", "Get Info", "Rename", "Compress “PennyWarden”", "Duplicate"].map((x) => x === "—" ? `<div style="height:1px;background:#d6d6d8;margin:4px 8px"></div>` : `<div style="padding:4px 10px">${x}</div>`).join("")}
        </div>
      </div>
    </div>`),
};

const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
const p = await browser.newPage({ viewport: { width: 900, height: 540 }, deviceScaleFactor: 2 });
for (const [name, html] of Object.entries(shots)) {
  await p.setContent(html);
  await p.screenshot({ path: join(OUT, name) });
  console.log("wrote", join("docs", "screenshots", "macos", name));
}
await browser.close();
