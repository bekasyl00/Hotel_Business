import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router.js";
import { configureTransport, createHttpTransport } from "@/shared/api";
import { isDemo, apiBase } from "@/shared/config";
import "./styles/catalog.css";
import "./styles/workspace.css";
if (isDemo) {
  const { createDemoTransport } = await import("./providers/demo.js");
  configureTransport(createDemoTransport());
} else configureTransport(createHttpTransport(apiBase));
const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
