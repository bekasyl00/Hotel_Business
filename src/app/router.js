import { h } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { useSessionStore } from "@/entities/session";
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("@/pages/catalog") },
    { path: "/staff/login", component: () => import("@/pages/login") },
    { path: "/staff", redirect: "/staff/overview" },
    {
      path: "/staff/:section",
      component: () => import("@/pages/workspace"),
      meta: { staff: true },
    },
    {
      path: "/:pathMatch(.*)*",
      component: {
        render: () =>
          h("main", { class: "work-empty" }, [
            h("h1", "Страница не найдена"),
            h("a", { href: "/" }, "Вернуться на сайт"),
          ]),
      },
    },
  ],
});
router.beforeEach(async (to) => {
  if (!to.meta.staff) return;
  const session = useSessionStore();
  try {
    await session.restore();
  } catch {
    return "/staff/login";
  }
  if (!session.user) return "/staff/login";
});
export default router;
