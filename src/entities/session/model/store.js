import { defineStore } from "pinia";
import { request } from "@/shared/api";
export const useSessionStore = defineStore("session", {
  state: () => ({ user: null, ready: false }),
  getters: { isAdmin: (s) => s.user?.role === "admin" },
  actions: {
    async restore() {
      this.user = await request("GET", "/auth/session");
      this.ready = true;
    },
    async login(payload) {
      this.user = await request("POST", "/auth/login", payload);
      this.ready = true;
    },
    async logout() {
      await request("POST", "/auth/logout");
      this.user = null;
      this.ready = true;
    },
  },
});
