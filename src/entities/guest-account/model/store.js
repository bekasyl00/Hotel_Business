import { defineStore } from "pinia";
import { request } from "@/shared/api";
export const useGuestAccountStore = defineStore("guest-account", {
  state: () => ({ session: null, ready: false }),
  getters: { authenticated: (state) => !!state.session?.authenticated },
  actions: {
    async restore() {
      this.session = await request("GET", "/guest-auth/session");
      this.ready = true;
      return this.session;
    },
    async login(payload) {
      this.session = await request("POST", "/guest-auth/login", payload);
      this.ready = true;
    },
    async register(payload) {
      this.session = await request("POST", "/guest-auth/register", payload);
      this.ready = true;
    },
    async logout() {
      this.session = await request("POST", "/guest-auth/logout", {});
      this.ready = true;
    },
    clear() {
      this.session = null;
      this.ready = false;
    },
  },
});
