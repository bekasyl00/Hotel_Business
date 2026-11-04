import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const manifest = async (dir) =>
  JSON.parse(await readFile(`${dir}/.vite/manifest.json`, "utf8"));
const site = await manifest("dist/site");
const staff = await manifest("dist/staff");
const includes = (entries, name) =>
  Object.keys(entries).some((key) => key.includes(`src/pages/${name}/`));
for (const name of ["workspace", "analytics", "staff-guest", "login"]) {
  assert.equal(
    includes(site, name),
    false,
    `Public build includes staff page: ${name}`,
  );
  assert.equal(includes(staff, name), true, `Staff build misses: ${name}`);
}
for (const name of [
  "catalog",
  "resort-profile",
  "room-profile",
  "guest-auth",
  "guest-profile",
]) {
  assert.equal(includes(site, name), true, `Public build misses: ${name}`);
  assert.equal(
    includes(staff, name),
    false,
    `Staff build includes public page: ${name}`,
  );
}
console.log("Public/staff build boundaries verified.");
