import { defineStore } from "pinia";
import { request } from "@/shared/api";
const restores = new WeakMap();
export const useGuestAccountStore = defineStore("guest-account", {
  state: () => ({ session: null, ready: false, revision: 0 }),
  getters: { authenticated: (state) => !!state.session?.authenticated },
  actions: {
    async restore() {
      const active = restores.get(this);
      if (active?.revision === this.revision) return active.promise;
      const revision = this.revision;
      const promise = request("GET", "/guest-auth/session")
        .then((session) => {
          if (this.revision === revision) {
            this.session = session;
            this.ready = true;
          }
          return this.session;
        })
        .finally(() => {
          if (restores.get(this)?.promise === promise) restores.delete(this);
        });
      restores.set(this, { revision, promise });
      return promise;
    },
    async login(payload) {
      const revision = ++this.revision;
      const session = await request("POST", "/guest-auth/login", payload);
      if (revision === this.revision) {
        this.revision += 1;
        this.session = session;
        this.ready = true;
      }
    },
    async register(payload) {
      const revision = ++this.revision;
      const session = await request("POST", "/guest-auth/register", payload);
      if (revision === this.revision) {
        this.revision += 1;
        this.session = session;
        this.ready = true;
      }
    },
    async logout() {
      const revision = ++this.revision;
      const session = await request("POST", "/guest-auth/logout", {});
      if (revision === this.revision) {
        this.revision += 1;
        this.session = session;
        this.ready = true;
      }
    },
    clear() {
      this.revision += 1;
      this.session = null;
      this.ready = false;
    },
  },
});
