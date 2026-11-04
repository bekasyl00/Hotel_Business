import { defineAsyncComponent } from "vue";
export { default as Modal } from "./Modal.vue";
export const GeoMap = defineAsyncComponent(() => import("./GeoMap.vue"));
export { default as LanguageSwitcher } from "./LanguageSwitcher.vue";

export { default as MediaEditor } from "./MediaEditor.vue";
