import { routes as staffRoutes } from "./routes-staff.js";
export const routes = [
  {
    path: "/staff/more",
    component: () => import("@/pages/staff-menu"),
    meta: { staff: true },
  },
  ...staffRoutes,
];
