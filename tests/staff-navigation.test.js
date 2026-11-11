import test from "node:test";
import assert from "node:assert/strict";
import { staffNavigation } from "../src/widgets/staff-shell/model/navigation.js";
import { createRouter, createMemoryHistory } from "vue-router";
import { staffRoutes } from "../src/app/routes-staff.js";
import { routes as mobileStaffRoutes } from "../src/app/routes-mobile-staff.js";
test("staff navigation has unique destinations and keeps accountant read-only destinations", () => {
  for (const role of ["admin", "manager", "accountant"]) {
    const paths = staffNavigation(role).map(([path]) => path);
    assert.equal(new Set(paths).size, paths.length);
    assert.equal(paths.includes("clients"), role === "admin");
    assert.equal(paths.includes("accounts"), role === "admin");
    assert.equal(paths.includes("history"), role === "admin");
    assert.equal(paths.includes("accounting"), role !== "manager");
    assert.equal(paths.includes("documents"), role !== "accountant");
    assert.equal(paths.includes("notifications"), role !== "accountant");
  }
  assert.deepEqual(
    staffNavigation("accountant").map(([path]) => path),
    ["accounting", "analytics", "bookings"],
  );
});
test("native staff management has an authenticated route distinct from workspace sections", () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: mobileStaffRoutes,
  });
  const route = router.resolve("/staff/more");
  assert.equal(route.matched[0].path, "/staff/more");
  assert.equal(route.meta.staff, true);
  assert.equal(route.meta.admin, undefined);
  assert.equal(route.meta.accounting, undefined);
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

test("document workspace has a separate operational staff route", () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: staffRoutes,
  });
  const route = router.resolve("/staff/documents");
  assert.equal(route.meta.staff, true);
  assert.equal(route.meta.documents, true);
  assert.equal(route.meta.accounting, undefined);
});
