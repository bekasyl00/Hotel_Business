import { defineStore } from "pinia";
import { request } from "@/shared/api";
export const useBookingStore = defineStore("bookings", {
  state: () => ({ items: [] }),
  actions: {
    async loadMine() {
      this.items = await request("GET", "/my-bookings");
    },
    async create(payload, staff = false) {
      return request("POST", staff ? "/bookings" : "/my-bookings", payload);
    },
    async cancel(booking, staff = false) {
      return request(
        "PATCH",
        `${staff ? "/bookings" : "/my-bookings"}/${booking.id}`,
        { status: "cancelled", version: booking.version },
      );
    },
  },
});
