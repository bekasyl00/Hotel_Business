import test from "node:test";
import assert from "node:assert/strict";
import { staffNavigation } from "../src/widgets/staff-shell/model/navigation.js";
test("staff navigation has unique destinations and keeps accountant read-only destinations", () => {
  for (const role of ["admin", "manager", "accountant"]) {
    const paths = staffNavigation(role).map(([path]) => path);
    assert.equal(new Set(paths).size, paths.length);
    assert.equal(paths.includes("clients"), role === "admin");
    assert.equal(paths.includes("accounts"), role === "admin");
  }
  assert.deepEqual(
    staffNavigation("accountant").map(([path]) => path),
    ["accounting", "analytics", "bookings"],
  );
});
