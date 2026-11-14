import { computed } from "vue";

export function useWorkspaceFilters({
  catalog,
  bookings,
  session,
  selected,
  query,
  status,
  accounts,
  audit,
  reviews,
  notifications,
}) {
  const current = computed(() =>
    catalog.resorts.find((r) => r.id === selected.value),
  );
  const scopedRooms = computed(() =>
    catalog.rooms.filter((r) => r.resortId === selected.value),
  );
  const scopedTariffs = computed(() =>
    catalog.tariffs.filter((t) => t.resortId === selected.value),
  );
  const scopedBookings = computed(() =>
    bookings.items.filter((b) => b.resortId === selected.value),
  );
  const matches = (item) =>
    Object.values(item)
      .filter((v) => typeof v === "string")
      .join(" ")
      .toLocaleLowerCase()
      .includes(query.value.toLocaleLowerCase());
  const filteredResorts = computed(() =>
    catalog.resorts
      .filter(matches)
      .filter((r) => status.value === "all" || r.status === status.value),
  );
  const filteredRooms = computed(() =>
    scopedRooms.value
      .filter(matches)
      .filter((r) => status.value === "all" || r.status === status.value),
  );
  const filteredBookings = computed(() =>
    scopedBookings.value
      .filter(matches)
      .filter(
        (r) =>
          status.value === "all" ||
          (status.value === "paid"
            ? r.status === "confirmed" &&
              r.payment?.status === "paid" &&
              r.stayStatus !== "checked_out"
            : status.value === "in_house"
              ? r.stayStatus === "in_house" && r.payment?.status === "paid"
              : status.value === "checked_out"
                ? r.stayStatus === "checked_out"
                : r.status === status.value),
      )
      .slice()
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
  );
  const filteredAudit = computed(() =>
    audit.value.filter(
      (a) =>
        (!selected.value ||
          a.resortId === selected.value ||
          (session.isAdmin && a.resortId === null)) &&
        matches(a),
    ),
  );
  const filteredReviews = computed(() =>
    reviews.value
      .filter((r) => r.resortId === selected.value)
      .filter(matches)
      .filter((r) => status.value === "all" || r.status === status.value),
  );
  const filteredNotifications = computed(() =>
    notifications.value
      .filter((n) => !selected.value || n.resortId === selected.value)
      .filter(matches)
      .filter(
        (n) =>
          status.value === "all" || (status.value === "unread" && !n.readAt),
      ),
  );
  const filteredAccounts = computed(() => accounts.value.filter(matches));
  return {
    current,
    scopedRooms,
    scopedTariffs,
    scopedBookings,
    filteredResorts,
    filteredRooms,
    filteredBookings,
    filteredAudit,
    filteredReviews,
    filteredNotifications,
    filteredAccounts,
  };
}
