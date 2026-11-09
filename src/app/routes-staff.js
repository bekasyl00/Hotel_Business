export const staffRoutes = [
  {
    path: "/staff/profile",
    component: () => import("@/pages/staff-profile"),
    meta: { staff: true },
  },
  {
    path: "/staff/:section(history|accounts)",
    component: () => import("@/pages/workspace"),
    meta: { staff: true, admin: true },
  },
  {
    path: "/staff/clients",
    component: () => import("@/pages/clients"),
    meta: { staff: true, admin: true },
  },
  {
    path: "/staff/accounting",
    component: () => import("@/pages/accounting"),
    meta: { staff: true, accounting: true },
  },
  {
    path: "/staff/documents",
    component: () => import("@/pages/staff-documents"),
    meta: { staff: true, documents: true },
  },
  { path: "/staff/tariffs", redirect: "/staff/rooms" },
  { path: "/staff/login", component: () => import("@/pages/login") },
  { path: "/staff", redirect: "/staff/bookings" },
  {
    path: "/staff/guests/:id",
    component: () => import("@/pages/staff-guest"),
    meta: { staff: true },
  },
  {
    path: "/staff/analytics",
    component: () => import("@/pages/analytics"),
    meta: { staff: true },
  },
  {
    path: "/staff/:section",
    component: () => import("@/pages/workspace"),
    meta: { staff: true },
  },
];
export const routes = [
  { path: "/", redirect: "/staff/bookings" },
  ...staffRoutes,
  {
    path: "/receipts/:id",
    component: () => import("@/pages/receipt"),
    meta: { staff: true },
  },
];
