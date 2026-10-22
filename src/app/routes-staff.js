export const staffRoutes = [
  { path: "/staff/login", component: () => import("@/pages/login") },
  { path: "/staff", redirect: "/staff/overview" },
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
  { path: "/", redirect: "/staff/overview" },
  ...staffRoutes,
  {
    path: "/receipts/:id",
    component: () => import("@/pages/receipt"),
    meta: { staff: true },
  },
];
