import { nextTick, onScopeDispose, ref, watch } from "vue";
import { request } from "../../../shared/api/index.js";
import { validateSearch } from "./rules.js";

export function useAvailability(dates) {
  const roomIds = ref(null);
  const searching = ref(false);
  const searchError = ref("");
  let generation = 0;

  function invalidate() {
    generation++;
    roomIds.value = null;
    searching.value = false;
    searchError.value = "";
  }

  async function checkDates() {
    const run = ++generation;
    searchError.value = validateSearch(dates);
    if (searchError.value) {
      roomIds.value = null;
      searching.value = false;
      return;
    }
    searching.value = true;
    try {
      const result = await request(
        "GET",
        "/availability?" + new URLSearchParams(dates),
      );
      if (run === generation) roomIds.value = result.roomIds;
    } catch (error) {
      if (run === generation) searchError.value = error.message;
    } finally {
      if (run === generation) searching.value = false;
    }
  }

  async function selectCalendarDates(range) {
    Object.assign(dates, range);
    await nextTick();
    await checkDates();
  }

  watch(dates, invalidate, { flush: "sync" });
  onScopeDispose(invalidate);
  return {
    roomIds,
    searching,
    searchError,
    checkDates,
    selectCalendarDates,
    invalidate,
  };
}
