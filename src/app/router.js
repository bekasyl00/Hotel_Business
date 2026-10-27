import { h } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { useSessionStore } from "@/entities/session";
import {
  appSurface,
  staffUrl,
  publicUrl,
  isMobile,
  isStaffApp,
  isDemo,
} from "@/shared/config";
import { useGuestAccountStore } from "@/entities/guest-account";
import { t } from "@/shared/i18n";
import { routes } from "#surface-routes";
import { routeLoadFailed } from "./route-errors.js";
const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || (to.path !== from.path ? { top: 0 } : undefined);
  },
  routes: [
    ...routes,
    {
      path: "/:pathMatch(.*)*",
      component: {
        render: () =>
          h("main", { class: "work-empty" }, [
            h("h1", t("common.notFound")),
            h(
              "a",
              {
                href: isStaffApp
                  ? "/staff/overview"
                  : isMobile
                    ? "/"
                    : publicUrl,
              },
              t("common.home"),
            ),
          ]),
      },
    },
  ],
});
router.beforeEach(async (to) => {
  if (
    isMobile &&
    !isStaffApp &&
    !isDemo &&
    /^\/(profile|bookings|receipts)(\/|$)/.test(to.path)
  ) {
    const guest = useGuestAccountStore();
    try {
      await guest.restore();
    } catch {
      guest.clear();
    }
    if (!guest.authenticated) return { path: "/account/login" };
  }
  if (
    appSurface === "public" &&
    to.path.startsWith("/staff") &&
    /^https?:\/\//.test(staffUrl)
  ) {
    window.location.assign(staffUrl);
    return false;
  }
  if (!to.meta.staff) return;
  const session = useSessionStore();
  try {
    await session.restore();
  } catch {
    return "/staff/login";
  }
  if (!session.user) return "/staff/login";
});
router.onError(() => {
  routeLoadFailed.value = true;
});
if (typeof window !== "undefined")
  window.addEventListener("vite:preloadError", (event) => {
    event.preventDefault();
    routeLoadFailed.value = true;
  });
export default router;
