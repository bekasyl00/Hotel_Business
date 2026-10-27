export const isDemo = import.meta.env.VITE_DATA_MODE !== "api";
export const apiBase = import.meta.env.VITE_API_BASE || "/api";
export const appSurface = import.meta.env.VITE_APP_SURFACE || "combined";
export const isMobile =
  appSurface === "mobile" || appSurface === "mobile-staff";
export const isStaffApp = appSurface === "mobile-staff";
export const isStaffSurface = appSurface === "staff" || isStaffApp;
export const staffUrl = import.meta.env.VITE_STAFF_URL || "/staff/login";
export const publicUrl = import.meta.env.VITE_PUBLIC_URL || "/";
