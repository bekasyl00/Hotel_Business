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
import { packageWeb } from "../scripts/package-web.mjs";

const configs = await Promise.all(
  ["vercel.json", "vercel.staff.json"].map(async (name) => ({
    name,
    value: JSON.parse(
      await readFile(new URL(`../${name}`, import.meta.url), "utf8"),
    ),
  })),
);

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
