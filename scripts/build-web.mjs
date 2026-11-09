import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { validateWebRelease } from "./package-web.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export function productionWebEnvironment(surface, current = process.env) {
  if (!["public", "staff"].includes(surface))
    throw new Error("Choose public or staff for a production website");
  return {
    ...current,
    VITE_DATA_MODE: "api",
    VITE_APP_SURFACE: surface,
    VITE_API_BASE: "/api",
    VITE_PUBLIC_URL: "https://vercel-site-puce-two.vercel.app",
    VITE_STAFF_URL: "https://tynys-staff.vercel.app/staff/login",
    VITE_UPLOAD_MAX_BYTES: "4000000",
  };
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    if (process.argv.length !== 3)
      throw new Error("Usage: node scripts/build-web.mjs <public|staff>");
    const surface = process.argv[2];
    Object.assign(process.env, productionWebEnvironment(surface));
    execFileSync(process.execPath, ["scripts/architecture.mjs"], {
      cwd: repository,
      stdio: "inherit",
    });
    await build({ root: repository, mode: surface });
    await validateWebRelease(surface === "public" ? "site" : "staff");
    console.log(`Production ${surface} website verified: API transport only.`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
