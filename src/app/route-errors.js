import { ref } from "vue";
export const routeLoadFailed = ref(false);
export const reloadApplication = () => window.location.reload();
