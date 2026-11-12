import { defineStore } from "pinia";
import { request } from "@/shared/api";
import { syncStaffPushSession, revokeStaffPushDevice } from "@/shared/native";
export const useSessionStore = defineStore("session", {
  state: () => ({ user: null, ready: false }),
  getters: {
    isAdmin: (s) => s.user?.role === "admin",
    isAccountant: (s) => s.user?.role === "accountant",
  },
  actions: {
    async restore() {
      this.user = await request("GET", "/auth/session");
      this.ready = true;
      await syncStaffPushSession(this.user, request);
    },
    async login(payload) {
      if (this.user) await revokeStaffPushDevice(request);
      this.user = await request("POST", "/auth/login", payload);
      this.ready = true;
      await syncStaffPushSession(this.user, request);
    },
    async logout() {
      await revokeStaffPushDevice(request);
      await request("POST", "/auth/logout");
      this.user = null;
      this.ready = true;
    },
  },
});
