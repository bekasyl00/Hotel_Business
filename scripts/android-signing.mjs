import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, chmod, access, writeFile, rename } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const directory = fileURLToPath(new URL("../native/android/signing/", import.meta.url));
await mkdir(directory, { recursive: true, mode: 0o700 });
await chmod(directory, 0o700);
for (const audience of ["guest", "staff"]) {
  const config = join(directory, `${audience}.properties`);
  const key = join(directory, `${audience}-distribution.p12`);
  const exists = async (path) => access(path).then(() => true, () => false);
  if (await exists(config)) {
    if (!(await exists(key))) throw new Error("Signing key is missing; restore its private backup");
    console.log(`${audience}: keeping the existing distribution key`);
    continue;
  }
  if (await exists(key)) throw new Error("An existing key has no configuration; do not overwrite it");
  const password = randomBytes(36).toString("base64url");
  const alias = `tynys-${audience}`;
  const temporary = `${key}.pending`;
  if (await exists(temporary)) throw new Error("Unfinished key generation exists; inspect it privately before retrying");
  try {
    execFileSync("keytool", [
      "-genkeypair", "-noprompt", "-keystore", temporary,
      "-storetype", "PKCS12", "-storepass:env", "TYNYS_SIGNING_PASSWORD",
      "-keypass:env", "TYNYS_SIGNING_PASSWORD", "-alias", alias,
      "-keyalg", "RSA", "-keysize", "4096", "-validity", "10000",
      "-dname", `CN=Tynys ${audience} application signing`,
    ], { env: { ...process.env, TYNYS_SIGNING_PASSWORD: password }, stdio: "pipe" });
    await chmod(temporary, 0o600);
    // Persist the recovery configuration before renaming the key into place.
    await writeFile(config, [
      `storeFile=${key}`, `storePassword=${password}`, `keyAlias=${alias}`, `keyPassword=${password}`, "",
    ].join("\n"), { mode: 0o600, flag: "wx" });
    await rename(temporary, key);
    console.log(`${audience}: private distribution key created; back up native/android/signing securely`);
  } catch {
    throw new Error(`${audience}: signing setup did not finish; inspect private files before retrying`);
  }
}
