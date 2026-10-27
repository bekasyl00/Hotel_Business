import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { loadConfig } from "@capacitor/cli/dist/config.js";
const variant = process.argv[2] || "guest";
assert(["guest", "staff"].includes(variant));
process.env.TYNYS_MOBILE_APP = variant;
const {
  app: { extConfig: config },
} = await loadConfig();
const staff = variant === "staff";
assert.equal(config.webDir, staff ? "dist/mobile-staff" : "dist/mobile");
assert.equal(config.appId, staff ? "kz.tynys.staff" : "kz.tynys.booking");
assert.equal(config.ios.path, staff ? "ios-staff" : "ios");
assert.equal(
  config.ios.scrollEnabled,
  true,
  "Native document must remain scrollable",
);
assert.equal(
  config.server?.url,
  undefined,
  "Bundle assets; never ship a live-reload URL",
);
assert.equal(config.server?.cleartext, undefined);
assert.equal(config.loggingBehavior, "none", "Bridge must not log credentials");
const entries = Object.keys(
  JSON.parse(await readFile(`${config.webDir}/.vite/manifest.json`, "utf8")),
);
const guestPages = ["catalog", "guest-profile", "guest-auth", "my-bookings"];
const staffPages = [
  "workspace",
  "analytics",
  "staff-guest",
  "login",
  "staff-menu",
];
for (const page of staff ? guestPages : staffPages)
  assert(
    !entries.some((k) => k.includes(`src/pages/${page}/`)),
    `Wrong audience page: ${page}`,
  );
for (const page of [...(staff ? staffPages : guestPages), "receipt"])
  assert(
    entries.some((k) => k.includes(`src/pages/${page}/`)),
    `Missing page: ${page}`,
  );
assert(
  entries.some((k) =>
    k.includes(staff ? "/staff-mobile-navigation/" : "/mobile-navigation/"),
  ),
);
console.log(
  `${variant}: bundle, route isolation and native configuration verified`,
);
