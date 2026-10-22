import { defineStore } from "pinia";
import { request } from "@/shared/api";
export const useResortStore = defineStore("resorts", {
  state: () => ({ resorts: [], rooms: [], tariffs: [] }),
  actions: {
    async loadPublic() {
      Object.assign(this, await request("GET", "/catalog"));
    },
    setData(data) {
      this.resorts = data.resorts;
      this.rooms = data.rooms;
      this.tariffs = data.tariffs;
    },
    clear() {
      this.resorts = [];
      this.rooms = [];
      this.tariffs = [];
    },
  },
});
