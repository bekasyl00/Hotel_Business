import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router.js";
import { configureTransport, createHttpTransport } from "@/shared/api";
import { isDemo, apiBase, isMobile, isStaffApp } from "@/shared/config";
import { i18n, syncDocumentLanguage } from "@/shared/i18n";
import "./styles/catalog.css";
import "./styles/workspace.css";
import "./styles/public-profiles.css";
if (isDemo) {
  const { createDemoTransport } = await import("./providers/demo.js");
  configureTransport(createDemoTransport());
} else if (isMobile) {
  const { createMobileTransport } = await import("./providers/mobile.js");
  configureTransport(
    createMobileTransport(apiBase, isStaffApp ? "staff" : "guest"),
  );
} else configureTransport(createHttpTransport(apiBase));
if (isMobile) {
  document.documentElement.classList.add("mobile-app");
  if (isStaffApp) document.documentElement.classList.add("mobile-staff-app");
  await import("./styles/mobile.css");
  const { isNative, clearReceiptCache } = await import("@/shared/native");
  if (isNative()) await clearReceiptCache();
}
const app = createApp(App);
app.use(i18n);
syncDocumentLanguage();
app.use(createPinia());
app.use(router);
app.mount("#app");
