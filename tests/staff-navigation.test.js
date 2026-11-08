import test from "node:test";
import assert from "node:assert/strict";
import { staffNavigation } from "../src/widgets/staff-shell/model/navigation.js";
import { createRouter, createMemoryHistory } from "vue-router";
import { staffRoutes } from "../src/app/routes-staff.js";
test("staff navigation has unique destinations and keeps accountant read-only destinations", () => {
  for (const role of ["admin", "manager", "accountant"]) {
    const paths = staffNavigation(role).map(([path]) => path);
    assert.equal(new Set(paths).size, paths.length);
    assert.equal(paths.includes("clients"), role === "admin");
    assert.equal(paths.includes("accounts"), role === "admin");
    assert.equal(paths.includes("history"), role === "admin");
  }
  assert.deepEqual(
    staffNavigation("accountant").map(([path]) => path),
    ["accounting", "analytics", "bookings"],
  );
});
test("direct history and accounts links resolve to admin-only workspace routes", () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: staffRoutes,
  });
  for (const section of ["history", "accounts"]) {
    const route = router.resolve(`/staff/${section}`);
    assert.equal(route.meta.staff, true);
    assert.equal(route.meta.admin, true);
    assert.equal(route.params.section, section);
  }
  assert.equal(router.resolve("/staff/bookings").meta.admin, undefined);
});
