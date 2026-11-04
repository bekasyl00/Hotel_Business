export const publicRoutes = [
  { path: "/", component: () => import("@/pages/catalog") },
  { path: "/resorts/:id", component: () => import("@/pages/resort-profile") },
  { path: "/rooms/:id", component: () => import("@/pages/room-profile") },
  { path: "/bookings", component: () => import("@/pages/my-bookings") },
  { path: "/profile", component: () => import("@/pages/guest-profile") },
  { path: "/receipts/:id", component: () => import("@/pages/receipt") },
  {
    path: "/account/login",
    component: () => import("@/pages/guest-auth"),
    meta: { authAction: "login" },
  },
  {
    path: "/account/register",
    component: () => import("@/pages/guest-auth"),
    meta: { authAction: "register" },
  },
  {
    path: "/account/reset-password",
    component: () => import("@/pages/guest-auth"),
    meta: { authAction: "reset" },
  },
];
export const routes = publicRoutes;
