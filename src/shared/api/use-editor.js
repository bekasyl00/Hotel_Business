import { ref } from "vue";
import { request } from "./index.js";
export function useEditor(resource, item, emit) {
  const busy = ref(false),
    error = ref("");
  async function save(payload) {
    if (busy.value) return;
    busy.value = true;
    error.value = "";
    try {
      const result = await request(
        item?.id ? "PATCH" : "POST",
        `/${resource}${item?.id ? "/" + item.id : ""}`,
        { ...payload, ...(item?.id ? { version: item.version } : {}) },
      );
      emit("saved", result);
    } catch (e) {
      error.value = e.message;
    } finally {
      busy.value = false;
    }
  }
  return { busy, error, save };
}
