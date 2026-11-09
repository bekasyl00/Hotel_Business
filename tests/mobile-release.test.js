import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  mobileReleaseEnvironment,
  validateMobileRelease,
} from "../scripts/build-mobile.mjs";

test("both iOS scene entry points load the controller that registers the secure session bridge", async () => {
  const bridge = await readFile(
    new URL("../native/ios/TynysViewController.swift", import.meta.url),
    "utf8",
  );
  assert.match(bridge, /class TynysViewController: CAPBridgeViewController/);
  assert.match(bridge, /registerPluginInstance\(TynysKeychain\(\)\)/);
  for (const root of ["ios", "ios-staff"]) {
    const scene = await readFile(
      new URL(`../${root}/App/App/SceneDelegate.swift`, import.meta.url),
      "utf8",
    );
    assert.match(scene, /rootViewController = TynysViewController\(\)/);
    assert.doesNotMatch(
      scene,
      /rootViewController = CAPBridgeViewController\(\)/,
    );
  }
});

test("installed guest and staff apps cannot inherit demo or website transport settings", () => {
  for (const audience of ["guest", "staff"]) {
    const env = mobileReleaseEnvironment(audience, {
      VITE_DATA_MODE: "demo",
      VITE_APP_SURFACE: "public",
      VITE_API_BASE: "/api",
    });
    assert.equal(env.VITE_DATA_MODE, "api");
    assert.equal(env.VITE_API_BASE, "https://tynys-api.vercel.app/api/v1");
    assert.equal(
      env.VITE_APP_SURFACE,
      audience === "staff" ? "mobile-staff" : "mobile",
    );
    assert.equal(env.TYNYS_MOBILE_APP, audience);
    assert.equal(env.VITE_UPLOAD_MAX_BYTES, "4000000");
  }
  assert.throws(() => mobileReleaseEnvironment("public"));
});

test("native release gate rejects a wrong backend, audience or demo transport", async () => {
  const root = await mkdtemp(join(tmpdir(), "tynys-native-release-"));
  try {
    for (const audience of ["guest", "staff"]) {
      const env = mobileReleaseEnvironment(audience, {});
      const metadata = join(root, "dist", env.VITE_APP_SURFACE, ".vite");
      await mkdir(metadata, { recursive: true });
      const release = {
        version: 1,
        surface: env.VITE_APP_SURFACE,
        dataMode: "api",
        apiBase: env.VITE_API_BASE,
      };
      const save = (data) =>
        writeFile(join(metadata, "release.json"), JSON.stringify(data));
      await writeFile(
        join(metadata, "manifest.json"),
        JSON.stringify({ "src/app/providers/mobile.js": {} }),
      );
      for (const overrides of [
        { dataMode: "demo" },
        { surface: "public" },
        { apiBase: "/api" },
      ]) {
        await save({ ...release, ...overrides });
        await assert.rejects(
          validateMobileRelease(audience, root),
          /shared HTTPS API/,
        );
      }
      await save(release);
      await validateMobileRelease(audience, root);
      await writeFile(
        join(metadata, "manifest.json"),
        JSON.stringify({
          "src/app/providers/mobile.js": {},
          "index.html": { dynamicImports: ["src/app/providers/demo.js"] },
        }),
      );
      await assert.rejects(validateMobileRelease(audience, root), /never demo/);
      await writeFile(join(metadata, "manifest.json"), "{}");
      await assert.rejects(
        validateMobileRelease(audience, root),
        /native transport/,
      );
    }
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
