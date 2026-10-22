import { watch } from "node:fs";
import { spawn, execFileSync } from "node:child_process";
function sync() {
  execFileSync(process.execPath, ["scripts/architecture.mjs"], {
    stdio: "inherit",
  });
}
sync();
const viewer = spawn(
  "node_modules/.bin/likec4",
  ["start", "architecture", "--port", "5174"],
  { stdio: "inherit" },
);
let timer;
const watcher = watch("src", () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    try {
      sync();
    } catch {
      console.error(
        "Architecture sync failed; fix the source dependency before continuing.",
      );
    }
  }, 250);
});
function close() {
  watcher.close();
  viewer.kill();
}
process.on("SIGINT", close);
process.on("SIGTERM", close);
viewer.on("exit", (code) => {
  watcher.close();
  process.exitCode = code || 0;
});
