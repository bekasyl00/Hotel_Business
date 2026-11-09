import test from "node:test";
import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { packageWeb, validateWebRelease } from "../scripts/package-web.mjs";
import { productionWebEnvironment } from "../scripts/build-web.mjs";

const configs = await Promise.all(
  ["vercel.json", "vercel.staff.json"].map(async (name) => ({
    name,
    value: JSON.parse(
      await readFile(new URL(`../${name}`, import.meta.url), "utf8"),
    ),
  })),
);

test("production web commands override conflicting demo and native build settings", () => {
  for (const surface of ["public", "staff"]) {
    const env = productionWebEnvironment(surface, {
      VITE_DATA_MODE: "demo",
      VITE_APP_SURFACE: "mobile",
      VITE_API_BASE: "https://wrong.example/api",
      VITE_UPLOAD_MAX_BYTES: "",
      VITE_PUBLIC_URL: "https://old.example",
      VITE_STAFF_URL: "https://old-staff.example",
    });
    assert.equal(env.VITE_DATA_MODE, "api");
    assert.equal(env.VITE_APP_SURFACE, surface);
    assert.equal(env.VITE_API_BASE, "/api");
    assert.equal(env.VITE_UPLOAD_MAX_BYTES, "4000000");
    assert.equal(
      env.VITE_PUBLIC_URL,
      "https://vercel-site-puce-two.vercel.app",
    );
    assert.equal(
      env.VITE_STAFF_URL,
      "https://tynys-staff.vercel.app/staff/login",
    );
  }
  assert.throws(() => productionWebEnvironment("mobile"), /public or staff/);
  assert.equal(configs[0].value.buildCommand, "npm run build:release:public");
  assert.equal(configs[1].value.buildCommand, "npm run build:release:staff");
});

test("release validation rejects stale metadata, demo transport and the wrong audience", async () => {
  const root = await mkdtemp(join(tmpdir(), "tynys-web-contract-"));
  try {
    for (const surface of ["site", "staff"]) {
      const metadata = join(root, "dist", surface, ".vite");
      await mkdir(metadata, { recursive: true });
      await writeFile(join(metadata, "manifest.json"), "{}");
      await assert.rejects(
        validateWebRelease(surface, root),
        /Missing website release/,
      );
      const release = {
        version: 1,
        surface: surface === "site" ? "public" : "staff",
        dataMode: "api",
        apiBase: "/api",
      };
      const save = (value) =>
        writeFile(join(metadata, "release.json"), JSON.stringify(value));
      for (const changed of [
        { dataMode: "demo" },
        { surface: "combined" },
        { apiBase: "https://other.example/api" },
        { version: 0 },
      ]) {
        await save({ ...release, ...changed });
        await assert.rejects(
          validateWebRelease(surface, root),
          /Only an API website/,
        );
      }
      await save(release);
      for (const manifest of [
        { "src/app/providers/demo.js": { file: "assets/demo-AbCd1234.js" } },
        { "index.html": { dynamicImports: ["src/app/providers/demo.js"] } },
      ]) {
        await writeFile(
          join(metadata, "manifest.json"),
          JSON.stringify(manifest),
        );
        await assert.rejects(
          validateWebRelease(surface, root),
          /Demo transport/,
        );
      }
      await writeFile(join(metadata, "manifest.json"), "{}");
      assert.deepEqual(await validateWebRelease(surface, root), {});
    }
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("only hashed assets have immutable caching; API paths are never cached", () => {
  for (const { value } of configs) {
    const headers = (path) => {
      const result = {};
      for (const route of value.routes) {
        if (route.src && new RegExp(`^(?:${route.src})$`).test(path)) {
          Object.assign(result, route.headers);
          if (!route.continue) break;
        }
      }
      return result;
    };
    for (const path of [
      "/api/profile",
      "/api/v1/bookings",
      "/api/availability",
      "/api/media/files/id",
      "/api/assets/fake-AbCd1234.js",
    ]) {
      const actual = headers(path);
      assert.equal(actual["Cache-Control"], "private, no-store");
      assert.equal(actual["CDN-Cache-Control"], "no-store");
      assert.equal(actual["Vercel-CDN-Cache-Control"], "no-store");
    }
    for (const path of [
      "/",
      "/index.html",
      "/staff/bookings",
      "/profile",
      "/resorts/fictional",
    ]) {
      assert.equal(
        headers(path)["Cache-Control"],
        "public, max-age=0, must-revalidate",
      );
    }
    assert.equal(
      headers("/assets/index-AbCd1234.js")["Cache-Control"],
      "public, max-age=31536000, immutable",
    );
    for (const path of [
      "/assets/logo.svg",
      "/assets/fonts/NotoSans-Regular.ttf",
      "/assets/room.jpg",
    ]) {
      assert.equal(headers(path)["Cache-Control"], undefined);
    }
  }
});

test("selected website packaging uses tracked proxy policy and excludes source, secrets and architecture", async () => {
  const root = await mkdtemp(join(tmpdir(), "tynys-web-package-"));
  try {
    const source = join(root, "dist/site");
    await mkdir(join(source, "assets"), { recursive: true });
    await mkdir(join(source, ".vite"));
    await writeFile(
      join(source, ".vite/release.json"),
      JSON.stringify({
        version: 1,
        surface: "public",
        dataMode: "api",
        apiBase: "/api",
      }),
    );
    const pages = [
      "catalog",
      "resort-profile",
      "room-profile",
      "guest-auth",
      "guest-profile",
    ];
    const manifest = Object.fromEntries(
      pages.map((name) => [`src/pages/${name}/ui/Page.vue`, {}]),
    );
    await writeFile(
      join(source, ".vite/manifest.json"),
      JSON.stringify(manifest),
    );
    await writeFile(join(source, "index.html"), "<html></html>");
    await writeFile(join(source, "assets/index-AbCd1234.js"), "export {};");
    await writeFile(join(source, ".env.local"), "fictional-secret-placeholder");
    await writeFile(
      join(source, "architecture.html"),
      "should not be published",
    );
    await writeFile(
      join(root, "vercel.json"),
      JSON.stringify(configs[0].value),
    );
    const target = await packageWeb("site", "output/site-release", root);
    assert.deepEqual((await readdir(target)).sort(), [
      "assets",
      "index.html",
      "vercel.json",
    ]);
    const config = JSON.parse(
      await readFile(join(target, "vercel.json"), "utf8"),
    );
    assert.deepEqual(config.routes, configs[0].value.routes);
    assert.equal(config.buildCommand, null);
    assert.equal(config.installCommand, null);
    assert.equal(config.outputDirectory, ".");
    await assert.rejects(
      packageWeb("site", "output/site-release", root),
      /EEXIST/,
    );
    manifest["src/pages/workspace/ui/Page.vue"] = {};
    await writeFile(
      join(source, ".vite/manifest.json"),
      JSON.stringify(manifest),
    );
    await assert.rejects(
      packageWeb("site", "output/wrong-surface", root),
      /audience/,
    );
    await assert.rejects(
      packageWeb("site", "dist/site", root),
      /new directory in output/,
    );
    await assert.rejects(
      packageWeb("mobile", "output/mobile", root),
      /exactly one website/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
