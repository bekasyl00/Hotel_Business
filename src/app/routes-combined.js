import { publicRoutes } from "./routes-public.js";
import { staffRoutes } from "./routes-staff.js";
export const routes = [...publicRoutes, ...staffRoutes];
