import { execFileSync } from "node:child_process";
import { access, copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { validateMobileRelease } from "./build-mobile.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const audience = process.argv[2];
if (!["guest", "staff"].includes(audience)) throw new Error("Choose guest or staff");
const bundle = process.argv[3] === "bundle";
const versionName = "1.1";
const versionCode = 8;
if (process.argv[3] && !bundle) throw new Error("Optional output must be bundle");
const project = join(root, audience === "staff" ? "android-staff" : "android");
const surface = audience === "staff" ? "mobile-staff" : "mobile";
await validateMobileRelease(audience, root);
await access(join(root, "native/android/signing", `${audience}.properties`));
const sdk = process.env.ANDROID_HOME || join(homedir(), "Library/Android/sdk");
const env = { ...process.env, ANDROID_HOME: sdk };
const config = JSON.parse(await readFile(join(project, "app/src/main/assets/capacitor.config.json"), "utf8"));
const appId = audience === "staff" ? "kz.tynys.staff" : "kz.tynys.booking";
if (config.appId !== appId || config.server?.url || config.server?.cleartext || config.loggingBehavior !== "none" ||
    config.android?.webContentsDebuggingEnabled !== false || config.android?.allowMixedContent !== false ||
    config.android?.minWebViewVersion !== 107 || config.server?.errorPath !== "native-update.html")
  throw new Error("Unsafe Android release configuration");
const bundledIndex = await readFile(join(project, "app/src/main/assets/public/index.html"));
if (!bundledIndex.equals(await readFile(join(root, "dist", surface, "index.html"))))
  throw new Error("Android assets are stale; run the corresponding release sync");
execFileSync(join(project, "gradlew"), [bundle ? ":app:bundleRelease" : ":app:assembleRelease", "--console=plain", "--max-workers=2"], {
  cwd: project, env, stdio: "inherit",
});
const output = join(root, "output/android");
await mkdir(output, { recursive: true });
const extension = bundle ? "aab" : "apk";
const source = join(project, bundle ? "app/build/outputs/bundle/release/app-release.aab" : "app/build/outputs/apk/release/app-release.apk");
if (!bundle) {
  const versions = (await readdir(join(sdk, "build-tools"))).sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
  const tools = join(sdk, "build-tools", versions[0]);
  execFileSync(join(tools, "apksigner"), ["verify", "--verbose", source], { env, stdio: "inherit" });
  const metadata = execFileSync(join(tools, "aapt"), ["dump", "badging", source], { env, encoding: "utf8" });
  if (!metadata.includes(`package: name='${appId}'`) || !metadata.includes("targetSdkVersion:'36'") || metadata.includes("application-debuggable") ||
      !metadata.includes(`versionCode='${versionCode}'`) || !metadata.includes(`versionName='${versionName}'`))
    throw new Error("Unexpected package, version, target API or debuggable release");
}
const name = `tynys-${audience}-${versionName}-${versionCode}.${extension}`;
await copyFile(source, join(output, name));
const checksum = createHash("sha256").update(await readFile(source)).digest("hex");
await writeFile(join(output, `${name}.sha256`), `${checksum}  ${name}\n`);
console.log(`${bundle ? "Built (Play verification pending)" : "Verified"} ${audience} ${extension}: ${join(output, name)}`);
