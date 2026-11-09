import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiBase = "https://tynys-api.vercel.app/api/v1";

export function mobileReleaseEnvironment(audience, current = process.env) {
  if (!["guest", "staff"].includes(audience))
    throw new Error("Choose guest or staff for an installed application");
  return {
    ...current,
    VITE_DATA_MODE: "api",
    VITE_APP_SURFACE: audience === "staff" ? "mobile-staff" : "mobile",
    VITE_API_BASE: apiBase,
    VITE_PUBLIC_URL: "https://vercel-site-puce-two.vercel.app",
    VITE_STAFF_URL: "https://tynys-staff.vercel.app/staff/login",
    VITE_UPLOAD_MAX_BYTES: "4000000",
    TYNYS_MOBILE_APP: audience,
  };
}

export async function validateMobileRelease(audience, root = repository) {
  const env = mobileReleaseEnvironment(audience, {});
  const output = resolve(root, "dist", env.VITE_APP_SURFACE);
  const release = JSON.parse(
    await readFile(resolve(output, ".vite/release.json"), "utf8"),
  );
  if (
    release.version !== 1 ||
    release.surface !== env.VITE_APP_SURFACE ||
    release.dataMode !== "api" ||
    release.apiBase !== apiBase
  )
    throw new Error(
      "Installed apps require their audience and the shared HTTPS API",
    );
  const manifest = JSON.parse(
    await readFile(resolve(output, ".vite/manifest.json"), "utf8"),
  );
  if (
    !manifest["src/app/providers/mobile.js"] ||
    Object.entries(manifest).some(([name, chunk]) =>
      [
        name,
        chunk.src,
        ...(chunk.imports || []),
        ...(chunk.dynamicImports || []),
      ]
        .filter(Boolean)
        .some((source) => source.startsWith("src/app/providers/demo")),
    )
  )
    throw new Error(
      "Installed apps must contain native transport, never demo transport",
    );
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    if (process.argv.length !== 3)
      throw new Error("Usage: node scripts/build-mobile.mjs <guest|staff>");
    const audience = process.argv[2];
    Object.assign(process.env, mobileReleaseEnvironment(audience));
    execFileSync(process.execPath, ["scripts/architecture.mjs"], {
      cwd: repository,
      stdio: "inherit",
    });
    await build({ root: repository, mode: process.env.VITE_APP_SURFACE });
    await validateMobileRelease(audience);
    execFileSync(process.execPath, ["scripts/check-mobile.mjs", audience], {
      cwd: repository,
      stdio: "inherit",
    });
    console.log(`${audience}: native API release verified`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
