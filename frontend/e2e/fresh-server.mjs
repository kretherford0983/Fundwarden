// Starts the backend with a brand-new temporary data directory (no initialization) for E2E runs.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const [, , py = "python", port = "8798"] = process.argv;
const dataDir = mkdtempSync(join(tmpdir(), "fmpoc-e2e-"));
const backend = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "backend");
// FM_BUNDLE=<path to packaged executable> runs the E2E suite against a self-contained build instead of source.
const bundle = process.env.FM_BUNDLE;
const cmd = bundle || py;
const args = bundle ? ["--no-browser", "--port", port, "--data-dir", dataDir] : ["-m", "fmpoc", "--no-browser", "--port", port, "--data-dir", dataDir];
const child = spawn(cmd, args, {
  cwd: backend, stdio: "inherit", env: { ...process.env, FM_LOGIN_MAX_FAILURES: "50",
    // 1.10.0 (#58): the update check reads a stand-in for pennywarden.org that the "#58" test serves on this port
    FM_UPDATE_CHANNEL: "stable", FM_UPDATE_BASE_URL: "http://127.0.0.1:8796" },
});
const stop = () => child.kill();
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
child.on("exit", (c) => process.exit(c ?? 0));
