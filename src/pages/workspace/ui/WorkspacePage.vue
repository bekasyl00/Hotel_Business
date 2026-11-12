<script setup>
import { useI18n } from "vue-i18n";
import {
  computed,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "@/entities/session";
import { useResortStore } from "@/entities/resort";
import { useBookingStore, propertyToday } from "@/entities/booking";
import { StaffShell } from "@/widgets/staff-shell";
import { Overview } from "@/widgets/overview";
import { ResortEditor } from "@/features/edit-resort";
import { RoomEditor } from "@/features/edit-room";
import { ClassPricingEditor } from "@/features/class-pricing";
import { ChildPolicyEditor } from "@/features/edit-child-policy";
import { OccupancyBoard, StayCard } from "@/widgets/occupancy-board";
import { AccountEditor } from "@/features/edit-account";
import { PaymentDialog } from "@/widgets/payment-dialog";
import { BookingEditor } from "@/features/create-booking";
import { isBankProvider } from "@/features/pay-booking";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import {
  staffPushState,
  pendingPushTarget,
  initStaffPushListeners,
  consumePendingPushTarget,
  openSystemNotificationSettings,
} from "@/shared/native";
import { money, dateLabel, timeLabel, statusNames } from "@/shared/lib";
import { isDemo, isStaffApp } from "@/shared/config";
const { t } = useI18n();
const paymentDialog = ref(null),
  stayCard = ref(null);
const canPayStaff = (b) =>
  !session.isAccountant &&
  b.source === "staff" &&
  ["pending", "confirmed"].includes(b.status) &&
  (!b.payment ||
    ["failed", "creating", "pending"].includes(b.payment.status)) &&
  (!b.holdExpiresAt ||
    b.status === "confirmed" ||
    Date.parse(b.holdExpiresAt) > Date.now()) &&
  Date.parse(b.cancellationPolicy?.checkinAt || "") > Date.now();
async function paymentSaved(result) {
  if (!result.failed) paymentDialog.value = null;
  await load(true);
}
const session = useSessionStore(),
  catalog = useResortStore(),
  bookings = useBookingStore();
const route = useRoute(),
  router = useRouter();
const section = computed(() => route.params.section || "overview");
const titles = computed(() => ({
  overview: t("staff.overviewTitle"),
  resorts: t("staff.resorts"),
  rooms: t("staff.inventory"),
  bookings: t("staff.board.title"),
  notifications: t("staff.notifications.title"),
  reviews: t("staff.guestReviews"),
  history: t("staff.history"),
  accounts: t("staff.managers"),
}));
const subtitles = computed(() => ({
  overview: t("staff.overviewSubtitle"),
  resorts: t("staff.resortsSubtitle"),
  rooms: t("staff.roomsSubtitle"),
  bookings: t("staff.board.subtitle"),
  notifications: t("staff.notifications.subtitle"),
  reviews: t("staff.reviewsSubtitle"),
  history: t("staff.historySubtitle"),
  accounts: t("staff.accountsSubtitle"),
}));
const selected = ref(""),
  query = ref(""),
  status = ref("all"),
  loading = ref(true),
  error = ref(""),
  notice = ref(""),
  accounts = ref([]),
  audit = ref([]),
  reviews = ref([]),
  notifications = ref([]),
  unreadNotifications = ref(0),
  editor = ref(null),
  confirm = ref(null),
  busy = ref(false);
const bookingView = ref("calendar"),
  focusedId = ref(null),
  detailError = ref("");
const focusedBooking = computed(() =>
  bookings.items.find(
    (b) => b.id === focusedId.value && b.resortId === selected.value,
  ),
);
function createAt(preset) {
  if (session.isAccountant) return;
  editor.value = { kind: "bookings", preset };
}
async function cardAction(action) {
  const booking = focusedBooking.value;
  if (!booking) return;
  if (action === "pay") {
    focusedId.value = null;
    paymentDialog.value = booking;
  } else if (action === "cancel") {
    focusedId.value = null;
    await prepareCancellation(booking);
  } else await changeStay(booking, action);
}
async function saveNotes(staffNotes) {
  busy.value = true;
  detailError.value = "";
  const booking = focusedBooking.value;
  try {
    await request("POST", `/bookings/${booking.id}/notes`, {
      version: booking.version,
      staffNotes,
    });
    notice.value = "staff.board.notesSaved";
    await load(true);
  } catch (e) {
    detailError.value = e.message;
  } finally {
    busy.value = false;
  }
}
watch(focusedId, () => {
  detailError.value = "";
});
watch(selected, () => {
  focusedId.value = null;
});
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
const stayNames = computed(() => ({
  not_arrived: t("staff.awaitingArrival"),
  in_house: t("staff.inHousePaid"),
  checked_out: t("staff.checkedOut"),
}));
function canCheckIn(booking) {
  const today = propertyToday(current.value?.timeZone || "Asia/Almaty");
  return (
    booking.status === "confirmed" &&
    booking.payment?.status === "paid" &&
    !booking.checkedInAt &&
    today >= booking.start &&
    today < booking.end
  );
}
async function changeStay(booking, action) {
  busy.value = true;
  error.value = "";
  try {
    await request("POST", `/bookings/${booking.id}/${action}`, {
      version: booking.version,
    });
    notice.value =
      action === "check-in" ? "staff.checkInNotice" : "staff.checkOutNotice";
    await load(true);
  } catch (e) {
    if (focusedId.value) detailError.value = e.message;
    else error.value = e.message;
  } finally {
    busy.value = false;
  }
}
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
    .filter((n) => status.value === "all" || (status.value === "unread" && !n.readAt)),
);
async function loadNotifications() {
  if (!session.user || session.isAccountant) return;
  try {
    const res = await request("GET", "/staff/notifications");
    notifications.value = res.items || [];
    unreadNotifications.value = Number(res.unreadCount || 0);
  } catch (e) {
    error.value = e.message;
  }
}
async function markNotificationRead(item) {
  if (item.readAt) return;
  try {
    const updated = await request(
      "POST",
      `/staff/notifications/${item.id}/read`,
      {},
    );
    const idx = notifications.value.findIndex((n) => n.id === item.id);
    if (idx >= 0) notifications.value[idx] = updated;
    unreadNotifications.value = notifications.value.filter(
      (n) => !n.readAt,
    ).length;
  } catch (e) {
    error.value = e.message;
  }
}
async function markAllNotificationsRead() {
  busy.value = true;
  error.value = "";
  try {
    const res = await request("POST", "/staff/notifications/read-all", {
      resortId: selected.value || undefined,
    });
    unreadNotifications.value = Number(res.unreadCount || 0);
    await loadNotifications();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function openNotificationBooking(item) {
  await markNotificationRead(item);
  if (item.resortId && item.resortId !== selected.value) {
    selected.value = item.resortId;
  }
  await router.push("/staff/bookings");
  bookingView.value = "calendar";
  if (item.bookingId) {
    focusedId.value = item.bookingId;
  }
}
async function applyDeepLinkBooking(list = bookings.items) {
  const queued = consumePendingPushTarget();
  const bookingId = String(
    queued?.bookingId || route.query.bookingId || "",
  ).trim();
  const resortId = String(
    queued?.resortId || route.query.resortId || "",
  ).trim();
  const notificationId = String(
    queued?.notificationId || route.query.notificationId || "",
  ).trim();
  if (!bookingId) return;

  if (notificationId && !session.isAccountant) {
    request("POST", `/staff/notifications/${notificationId}/read`, {}).catch(
      () => {},
    );
  }
  const match = (list || []).find((b) => String(b.id) === bookingId);
  const targetResortId = match?.resortId || resortId;
  if (
    targetResortId &&
    catalog.resorts.some((r) => r.id === targetResortId) &&
    selected.value !== targetResortId
  ) {
    selected.value = targetResortId;
  }
  if (section.value !== "bookings") {
    await router.replace({ path: "/staff/bookings", query: {} });
  } else if (
    route.query.bookingId ||
    route.query.resortId ||
    route.query.notificationId
  ) {
    const rest = { ...route.query };
    delete rest.bookingId;
    delete rest.resortId;
    delete rest.notificationId;
    await router.replace({ query: rest });
  }
  bookingView.value = "calendar";
  await nextTick();
  if (match) {
    focusedId.value = match.id;
  }
}
async function moderateReview(review, target) {
  busy.value = true;
  error.value = "";
  try {
    await request("PATCH", `/reviews/${review.id}`, {
      version: review.version,
      status: target,
      reply: review.reply || "",
    });
    notice.value = "staff.reviewUpdated";
    await load(true);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function prepareCancellation(item) {
  busy.value = true;
  error.value = "";
  try {
    const preview = await request(
      "GET",
      `/cancellation-preview/${item.id}?asStaff=true`,
    );
    confirm.value = {
      kind: "bookings",
      item,
      title: t("staff.cancelBookingTitle"),
      text: `${t("staff.cancellationPreview", { refund: money(preview.refundAmount), paid: money(preview.paidAmount) })} ${t("staff.refundSchedule")}`,
    };
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
const filteredAccounts = computed(() => accounts.value.filter(matches));
const canAdd = computed(
  () =>
    !session.isAccountant &&
    (["resorts", "accounts"].includes(section.value)
      ? session.isAdmin
      : ["rooms", "bookings"].includes(section.value) &&
        current.value &&
        current.value.status !== "archived"),
);
const addLabels = computed(() => ({
  resorts: t("staff.createResort"),
  rooms: t("staff.addRoom"),
  bookings: t("staff.addBooking"),
  accounts: t("staff.addManager"),
}));
let generation = 0;
async function load(quiet = false) {
  const run = ++generation;
  if (!quiet) loading.value = true;
  error.value = "";
  try {
    await session.restore();
    if (!session.user) return router.replace("/staff/login");
    const data = await request("GET", "/workspace");
    if (run !== generation) return;
    catalog.setData(data);
    bookings.items = data.bookings;
    if (typeof route.query.paymentReturn === "string") {
      paymentDialog.value =
        data.bookings.find(
          (b) =>
            b.source === "staff" && b.payment?.id === route.query.paymentReturn,
        ) || null;
      const { paymentReturn, ...query } = route.query;
      await router.replace({ query });
    }
    accounts.value = session.isAdmin ? data.accounts : [];
    audit.value = session.isAdmin ? data.audit : [];
    reviews.value = data.reviews || [];
    unreadNotifications.value = Number(
      data.unreadNotificationCount ?? data.unreadNotifications ?? 0,
    );
    if (!session.isAccountant && section.value === "notifications") {
      await loadNotifications();
    }
    if (!catalog.resorts.some((r) => r.id === selected.value))
      selected.value =
        catalog.resorts.find((r) => r.status !== "archived")?.id ||
        catalog.resorts[0]?.id ||
        "";
    await applyDeepLinkBooking(data.bookings);
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function logout() {
  if (stayCard.value && !stayCard.value.canLeave()) return;
  focusedId.value = null;
  await nextTick();
  try {
    await session.logout();
    catalog.clear();
    bookings.items = [];
    await router.replace("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
function open(kind = section.value, item = null) {
  notice.value = "";
  editor.value = { kind, item };
}
async function saved(record) {
  editor.value = null;
  notice.value = "staff.changesSaved";
  if (section.value === "resorts" && record?.id) selected.value = record.id;
  await load(true);
  if (section.value === "bookings" && record?.id) focusedId.value = record.id;
}
async function act() {
  busy.value = true;
  try {
    const { kind, item } = confirm.value;
    await request(
      kind === "bookings" ? "PATCH" : "DELETE",
      `/${kind}/${item.id}`,
      {
        version: item.version,
        ...(kind === "bookings"
          ? { status: confirm.value.target || "cancelled" }
          : {}),
      },
    );
    confirm.value = null;
    notice.value = "staff.changeLogged";
    await load(true);
  } catch (e) {
    confirm.value.error = e.message;
  } finally {
    busy.value = false;
  }
}
function switchResort(id) {
  selected.value = id;
  router.push("/staff/rooms");
}
function changes(entry) {
  const keys = new Set([
    ...Object.keys(entry.before || {}),
    ...Object.keys(entry.after || {}),
  ]);
  return [...keys]
    .filter(
      (k) =>
        !["id", "version", "rating", "ownerId"].includes(k) &&
        JSON.stringify(entry.before?.[k]) !== JSON.stringify(entry.after?.[k]),
    )
    .map((key) => ({
      key,
      before: entry.before?.[key],
      after: entry.after?.[key],
    }));
}
const fieldNames = computed(() => ({
  notesLength: t("staff.board.notesLength"),
  checkInTime: t("staff.checkInTime"),
  timeZone: t("staff.timeZone"),
  resortClass: t("staff.class"),
  priceKind: t("staff.priceKind"),
  discountPercent: t("staff.discount"),
  payment: t("staff.payment"),
  cancellationPolicy: t("staff.refundTerms"),
  cancellation: t("staff.cancellationResult"),
  guestProfileId: t("staff.guestProfile"),
  checkedInAt: t("staff.actualArrival"),
  checkedOutAt: t("staff.actualDeparture"),
  stayStatus: t("staff.stayStatus"),
  name: t("staff.name"),
  status: t("staff.status"),
  price: t("staff.price"),
  supplement: t("staff.supplement"),
  number: t("staff.room"),
  capacity: t("staff.capacity"),
  area: t("staff.area"),
  lat: t("staff.latitude"),
  lng: t("staff.longitude"),
  address: t("staff.address"),
  city: t("staff.city"),
  description: t("staff.description"),
  subtitle: t("staff.shortDescription"),
  feature: t("staff.service"),
  features: t("staff.services"),
  beds: t("staff.beds"),
  category: t("staff.category"),
  title: t("staff.name"),
  login: t("staff.login"),
  resortId: t("staff.resort"),
  start: t("staff.arrival"),
  end: t("staff.departure"),
  guests: t("staff.guests"),
  total: t("staff.amount"),
  guestLabel: t("staff.guest"),
  roomId: t("staff.physicalRoom"),
  tariffId: t("staff.tariff"),
}));
const display = (value) =>
  value == null
    ? "—"
    : Array.isArray(value)
      ? value.join(", ")
      : typeof value === "object"
        ? JSON.stringify(value)
        : statusNames[value] ||
          {
            regular: t("staff.regularPrice"),
            discount: t("staff.discountPrice"),
            not_arrived: t("staff.awaitingArrival"),
            in_house: t("staff.inHousePaid"),
            checked_out: t("staff.checkedOut"),
            website: t("staff.website"),
            staff: t("staff.manual"),
          }[value] ||
          String(value);
watch(section, (next) => {
  query.value = "";
  status.value = "all";
  editor.value = null;
  if (!route.query.bookingId && !pendingPushTarget.value?.bookingId) {
    focusedId.value = null;
  }
  if (next === "notifications" && !session.isAccountant) {
    loadNotifications();
  }
});
watch(
  () => [route.query.bookingId, pendingPushTarget.value?.bookingId],
  ([qId, pId]) => {
    if ((qId || pId) && !loading.value && bookings.items.length) {
      applyDeepLinkBooking(bookings.items);
    }
  },
);
const storageChanged = (e) => {
  if (e.key === "tynys:workspace:v2") load();
};
onMounted(() => {
  initStaffPushListeners((target) => {
    if (target?.bookingId && !loading.value && bookings.items.length) {
      applyDeepLinkBooking(bookings.items);
    }
  });
  load();
  window.addEventListener("storage", storageChanged);
});
onBeforeUnmount(() => {
  generation++;
  window.removeEventListener("storage", storageChanged);
});
</script>
<template>
  <StaffShell
    :section="section"
    :unread-count="unreadNotifications"
    @logout="logout"
    @unread="unreadNotifications = $event"
    ><main
      class="work-main"
      :class="{ 'planner-workspace': section === 'bookings' }"
    >
      <div v-if="isDemo" class="demo-strip">
        <span class="demo-dot"></span
        >{{
          t(isStaffApp ? "common.mobile.demoWorkspace" : "staff.demoWorkspace")
        }}
      </div>
      <div
        v-if="
          !titles[section] ||
          (['accounts', 'history'].includes(section) && !session.isAdmin) ||
          (section === 'notifications' && session.isAccountant)
        "
        class="surface work-empty"
      >
        <h1>{{ t("staff.sectionUnavailable") }}</h1>
        <p>{{ t("staff.availableSectionHint") }}</p>
        <RouterLink to="/staff/overview">{{
          t("staff.backToOverview")
        }}</RouterLink>
      </div>
      <template v-else
        ><div class="work-title">
          <div>
            <span class="eyebrow">{{
              session.isAdmin ? t("staff.platformManagement") : current?.name
            }}</span>
            <h1>
              {{
                section === "resorts" && !session.isAdmin
                  ? t("staff.myResort")
                  : titles[section]
              }}
            </h1>
            <p>{{ subtitles[section] }}</p>
          </div>
          <button
            v-if="canAdd"
            class="primary"
            :disabled="loading"
            @click="open()"
          >
            ＋ {{ addLabels[section] }}
          </button>
        </div>
        <p v-if="notice" class="success-notice" role="status">
          ✓ {{ t(notice) }}
        </p>
        <div
          v-if="!session.isAccountant && staffPushState.permission === 'denied'"
          class="error-panel"
          role="status"
          data-testid="push-permission-denied"
        >
          <div>
            <strong>{{ t("staff.notifications.pushDeniedTitle") }}</strong>
            <p>{{ t("staff.notifications.pushDeniedBody") }}</p>
          </div>
          <button
            type="button"
            class="secondary"
            @click="openSystemNotificationSettings"
          >
            {{ t("staff.notifications.openSystemSettings") }}
          </button>
        </div>
        <div v-if="error" class="error-panel" role="alert">
          <p>{{ error }}</p>
          <button class="secondary" @click="load">
            {{ t("staff.retryLoading") }}
          </button>
        </div>
        <p v-if="loading" class="loading-panel" role="status">
          {{ t("staff.loadingWorkspace") }}
        </p>
        <template v-else-if="!error"
          ><div
            v-if="
              [
                'rooms',
                'bookings',
                'notifications',
                'reviews',
                'history',
              ].includes(section)
            "
            class="context-bar"
          >
            <label
              >{{ t("staff.resort")
              }}<select
                v-model="selected"
                :disabled="catalog.resorts.length < 2"
              >
                <option v-if="!catalog.resorts.length" value="">
                  {{ t("staff.noResorts") }}
                </option>
                <option v-for="r in catalog.resorts" :key="r.id" :value="r.id">
                  {{ r.name
                  }}{{
                    r.status === "archived" ? t("staff.archivedSuffix") : ""
                  }}
                </option>
              </select></label
            ><span v-if="current" :class="['status-pill', current.status]">{{
              statusNames[current.status]
            }}</span
            ><span v-if="current" class="context-count">{{
              t("staff.board.roomCount", { count: scopedRooms.length })
            }}</span>
            <div v-if="section === 'bookings'" class="board-view-toggle">
              <button
                class="secondary"
                :aria-pressed="bookingView === 'calendar'"
                @click="bookingView = 'calendar'"
              >
                ▦ {{ t("staff.board.calendar") }}</button
              ><button
                class="secondary"
                :aria-pressed="bookingView === 'list'"
                @click="bookingView = 'list'"
              >
                ☷ {{ t("staff.board.list") }}
              </button>
            </div>
            <button
              v-if="section === 'rooms' && current && !session.isAccountant"
              type="button"
              class="secondary"
              :disabled="current.status === 'archived'"
              @click="open('class-pricing')"
            >
              {{ t("common.classPricing.open") }}
            </button>
            <button
              v-if="section === 'rooms' && current && !session.isAccountant"
              type="button"
              class="secondary"
              :disabled="current.status === 'archived'"
              @click="open('child-policy')"
            >
              {{ t("common.children.settingsTitle") }}
            </button>
          </div>
          <Overview
            v-if="section === 'overview'"
            :resorts="catalog.resorts"
            :rooms="catalog.rooms"
            :bookings="bookings.items"
            @bookings="router.push('/staff/bookings')"
            @create="current ? open('bookings') : router.push('/staff/resorts')"
          />
          <template v-else>
            <OccupancyBoard
              :read-only="session.isAccountant"
              v-if="section === 'bookings' && bookingView === 'calendar'"
              :key="selected"
              :resort="current"
              :rooms="scopedRooms"
              :bookings="scopedBookings"
              :busy="busy"
              @refresh="load(true)"
              @select="focusedId = $event.id"
              @create="createAt"
            />
            <section v-else class="surface">
              <div class="table-toolbar">
                <label class="search-field"
                  ><span aria-hidden="true">⌕</span
                  ><input
                    v-model="query"
                    type="search"
                    :placeholder="
                      section === 'history'
                        ? t('staff.searchAudit')
                        : t('staff.searchSectionPlaceholder')
                    "
                    :aria-label="t('staff.searchSection')" /></label
                ><label v-if="!['history', 'accounts'].includes(section)"
                  ><span class="sr-only">{{ t("staff.recordStatus") }}</span
                  ><select
                    v-model="status"
                    :aria-label="t('staff.recordStatus')"
                  >
                    <option value="all">{{ t("staff.allStatuses") }}</option>
                    <template v-if="section === 'resorts'"
                      ><option value="published">
                        {{ t("staff.published") }}
                      </option>
                      <option value="draft">{{ t("staff.draft") }}</option>
                      <option value="archived">
                        {{ t("staff.archived") }}
                      </option></template
                    ><template v-else-if="section === 'bookings'"
                      ><option value="pending">{{ t("staff.pending") }}</option>
                      <option value="rejected">
                        {{ t("staff.bookingRejected") }}
                      </option>
                      <option value="expired">
                        {{ t("common.status.expired") }}
                      </option>
                      <option value="confirmed">
                        {{ t("staff.confirmed") }}
                      </option>
                      <option value="paid">
                        {{ t("staff.paidActive") }}
                      </option>
                      <option value="in_house">
                        {{ t("staff.inHouseFilter") }}
                      </option>
                      <option value="checked_out">
                        {{ t("staff.checkedOutFilter") }}
                      </option>
                      <option value="cancelled">
                        {{ t("staff.cancelled") }}
                      </option></template
                    ><template v-else-if="section === 'reviews'"
                      ><option value="pending">
                        {{ t("staff.underReview") }}
                      </option>
                      <option value="approved">
                        {{ t("staff.published") }}
                      </option>
                      <option value="rejected">
                        {{ t("staff.rejected") }}
                      </option></template
                    ><template v-else-if="section === 'notifications'"
                      ><option value="unread">
                        {{ t("staff.notifications.unreadOnly") }}
                      </option></template
                    ><template v-else
                      ><option value="active">{{ t("staff.active") }}</option>
                      <option
                        :value="
                          section === 'rooms' ? 'maintenance' : 'disabled'
                        "
                      >
                        {{
                          section === "rooms"
                            ? t("staff.maintenance")
                            : t("staff.disabled")
                        }}
                      </option></template
                    >
                  </select></label
                ><button
                  v-if="section === 'notifications' && unreadNotifications > 0"
                  type="button"
                  class="secondary"
                  :disabled="busy"
                  @click="markAllNotificationsRead"
                >
                  {{ t("staff.notifications.markAllRead") }}
                </button>
                <button
                  class="text-button"
                  @click="load"
                  :aria-label="t('staff.refreshData')"
                >
                  {{ t("staff.refresh") }}
                </button>
              </div>
              <div
                v-if="
                  section === 'notifications' && filteredNotifications.length
                "
                class="audit-list"
              >
                <article
                  v-for="item in filteredNotifications"
                  :key="item.id"
                  class="staff-review"
                  :style="{
                    borderLeft: item.readAt
                      ? '3px solid #cbd6cf'
                      : '4px solid #143e2c',
                  }"
                >
                  <div class="row-actions" style="justify-content: space-between">
                    <strong
                      >{{ item.title }} ·
                      {{ t(`staff.notifications.${item.kind}`) }}</strong
                    >
                    <small>{{ timeLabel(item.createdAt) }}</small>
                  </div>
                  <p>{{ item.body }}</p>
                  <div class="row-actions">
                    <button
                      v-if="item.bookingId"
                      type="button"
                      class="primary"
                      @click="openNotificationBooking(item)"
                    >
                      {{ t("staff.notifications.openBooking") }}
                    </button>
                    <button
                      v-if="!item.readAt"
                      type="button"
                      class="secondary"
                      @click="markNotificationRead(item)"
                    >
                      {{ t("staff.notifications.markRead") }}
                    </button>
                  </div>
                </article>
              </div>
              <div
                v-else-if="section === 'resorts' && filteredResorts.length"
                class="table-scroll"
                tabindex="0"
                role="region"
                :aria-label="t('staff.dataTable')"
              >
                <table class="workspace-table">
                  <thead>
                    <tr>
                      <th>{{ t("staff.resort") }}</th>
                      <th>{{ t("staff.location") }}</th>
                      <th>{{ t("staff.rooms") }}</th>
                      <th>{{ t("staff.status") }}</th>
                      <th>{{ t("staff.actions") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in filteredResorts" :key="r.id">
                      <td :data-label="t('staff.resort')">
                        <div class="property-cell">
                          <img
                            src="/assets/resort.jpg"
                            :alt="t('staff.resortIllustration')"
                          />
                          <div>
                            <strong>{{ r.name }}</strong
                            ><small>{{
                              r.subtitle || t("staff.descriptionMissing")
                            }}</small>
                            <small v-if="session.isAdmin"
                              >{{ t("staff.directory.owner") }}:
                              {{
                                accounts.find(
                                  (a) => a.id === String(r.accountId),
                                )?.name || "—"
                              }}</small
                            >
                          </div>
                        </div>
                      </td>
                      <td :data-label="t('staff.location')">
                        {{ r.city }}<small>{{ r.address }}</small>
                      </td>
                      <td :data-label="t('staff.rooms')">
                        <button class="text-button" @click="switchResort(r.id)">
                          {{
                            t("staff.roomsLink", {
                              count: catalog.rooms.filter(
                                (x) => x.resortId === r.id,
                              ).length,
                            })
                          }}
                        </button>
                      </td>
                      <td :data-label="t('staff.status')">
                        <span :class="['status-pill', r.status]">{{
                          statusNames[r.status]
                        }}</span>
                      </td>
                      <td :data-label="t('staff.actions')">
                        <div class="row-actions">
                          <button
                            v-if="r.status !== 'archived'"
                            class="text-button"
                            @click="open('resorts', r)"
                          >
                            {{ t("staff.configure") }}</button
                          ><button
                            v-if="session.isAdmin && r.status !== 'archived'"
                            class="text-button danger"
                            @click="
                              confirm = {
                                kind: 'resorts',
                                item: r,
                                title: t('staff.archiveTitle'),
                                text: t('staff.archiveText'),
                              }
                            "
                          >
                            {{ t("staff.archive") }}
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div
                v-else-if="section === 'rooms' && filteredRooms.length"
                class="table-scroll"
                tabindex="0"
                role="region"
                :aria-label="t('staff.dataTable')"
              >
                <table class="workspace-table">
                  <thead>
                    <tr>
                      <th>{{ t("staff.physicalRoom") }}</th>
                      <th>{{ t("staff.category") }}</th>
                      <th>{{ t("staff.capacity") }}</th>
                      <th>{{ t("staff.perNight") }}</th>
                      <th>{{ t("staff.status") }}</th>
                      <th>{{ t("staff.actions") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in filteredRooms" :key="r.id">
                      <td :data-label="t('staff.physicalRoom')">
                        <strong>№ {{ r.number }}</strong
                        ><small
                          >{{ r.area }} {{ t("staff.squareMetres") }}</small
                        >
                      </td>
                      <td :data-label="t('staff.category')">
                        {{ r.title }}<small>{{ r.beds }}</small>
                      </td>
                      <td :data-label="t('staff.capacity')">
                        {{ t("staff.guestCount", { count: r.capacity }) }}
                      </td>
                      <td :data-label="t('staff.perNight')" class="numeric">
                        {{ money(r.price) }}
                      </td>
                      <td :data-label="t('staff.status')">
                        <span :class="['status-pill', r.status]">{{
                          statusNames[r.status]
                        }}</span>
                      </td>
                      <td :data-label="t('staff.actions')">
                        <div class="row-actions">
                          <button class="text-button" @click="open('rooms', r)">
                            {{ t("staff.edit") }}</button
                          ><button
                            class="text-button danger"
                            @click="
                              confirm = {
                                kind: 'rooms',
                                item: r,
                                title: t('staff.deleteRoomTitle', {
                                  number: r.number,
                                }),
                                text: t('staff.deleteRoomText'),
                              }
                            "
                          >
                            {{ t("staff.delete") }}
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div
                v-else-if="section === 'bookings' && filteredBookings.length"
                class="table-scroll"
                tabindex="0"
                role="region"
                :aria-label="t('staff.dataTable')"
              >
                <table class="workspace-table">
                  <thead>
                    <tr>
                      <th>{{ t("staff.bookingGuest") }}</th>
                      <th>{{ t("staff.room") }}</th>
                      <th>{{ t("staff.dates") }}</th>
                      <th>{{ t("staff.amount") }}</th>
                      <th>{{ t("staff.status") }}</th>
                      <th>{{ t("staff.action") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="b in filteredBookings" :key="b.id">
                      <td :data-label="t('staff.bookingGuest')">
                        <RouterLink
                          v-if="b.guestProfileId && !session.isAccountant"
                          :to="`/staff/guests/${b.guestProfileId}`"
                          ><strong>{{ b.guestLabel }}</strong></RouterLink
                        >
                        <button
                          v-else
                          class="text-button"
                          @click="focusedId = b.id"
                        >
                          <strong>{{ b.guestLabel }}</strong></button
                        ><small v-if="b.guestPhone">{{ b.guestPhone }}</small
                        ><small
                          >#{{ b.id.slice(0, 8) }} ·
                          {{
                            b.source === "staff"
                              ? t("staff.manual")
                              : t("staff.website")
                          }}</small
                        >
                      </td>
                      <td :data-label="t('staff.room')">
                        № {{ b.unit }} · {{ b.roomName
                        }}<small>{{
                          t("staff.guestCount", { count: b.guests })
                        }}</small>
                      </td>
                      <td :data-label="t('staff.dates')">
                        {{ dateLabel(b.start)
                        }}<small>{{
                          t("staff.untilDate", { date: dateLabel(b.end) })
                        }}</small>
                      </td>
                      <td :data-label="t('staff.amount')" class="numeric">
                        {{ money(b.paymentTerms?.total ?? b.total)
                        }}<small v-if="b.payment"
                          >{{
                            isBankProvider(b.payment.provider)
                              ? t(
                                  `common.payment.states.${b.payment.checkoutStatus}`,
                                )
                              : b.payment.status === "paid"
                                ? t("staff.demoPaid")
                                : ["failed", "creating", "pending"].includes(
                                      b.payment.status,
                                    )
                                  ? t("staff.demoFailed")
                                  : t("staff.demoRefunded")
                          }}<span v-if="b.payment.refundedAmount">
                            {{ money(b.payment.refundedAmount) }}</span
                          ></small
                        >
                        <RouterLink
                          v-if="b.payment?.receiptUrl && !session.isAccountant"
                          class="receipt-link"
                          :to="b.payment.receiptUrl"
                          >{{ t("staff.openReceipt") }}</RouterLink
                        >
                      </td>
                      <td :data-label="t('staff.status')">
                        <span :class="['status-pill', b.status]">{{
                          statusNames[b.status]
                        }}</span>
                        <small v-if="b.status === 'confirmed'">{{
                          stayNames[b.stayStatus || "not_arrived"]
                        }}</small>
                        <small
                          v-if="b.status === 'pending' && b.holdExpiresAt"
                          >{{
                            t("common.checkout.payBefore", {
                              date: timeLabel(b.holdExpiresAt),
                            })
                          }}</small
                        >
                        <small v-if="b.commissionTerms"
                          >{{ t("common.checkout.commissionEstimate") }}:
                          {{
                            b.commissionTerms.amount == null
                              ? t("common.checkout.notConfigured")
                              : money(b.commissionTerms.amount)
                          }}</small
                        >
                        <small v-if="b.commissionTerms?.resortAmount != null"
                          >{{ t("common.checkout.resortEstimate") }}:
                          {{ money(b.commissionTerms.resortAmount) }}</small
                        >
                        <small
                          v-if="b.commissionTerms && b.payment?.refundedAmount"
                          >{{
                            t("common.checkout.refundReconciliation")
                          }}</small
                        >
                        <small v-if="b.checkedInAt">{{
                          t("staff.arrivalAt", {
                            date: timeLabel(b.checkedInAt),
                          })
                        }}</small>
                        <small v-if="b.checkedOutAt">{{
                          t("staff.departureAt", {
                            date: timeLabel(b.checkedOutAt),
                          })
                        }}</small>
                      </td>
                      <td :data-label="t('staff.action')">
                        <div
                          v-if="!session.isAccountant && b.status === 'pending'"
                          class="row-actions"
                        >
                          <button
                            v-if="canPayStaff(b)"
                            class="text-button"
                            @click="paymentDialog = b"
                          >
                            {{
                              t(
                                isDemo
                                  ? "common.checkout.demoPay"
                                  : "common.payment.title",
                              )
                            }}
                          </button>
                          <button
                            class="text-button danger"
                            :disabled="busy"
                            @click="prepareCancellation(b)"
                          >
                            {{ t("staff.cancelBooking") }}
                          </button>
                        </div>
                        <div
                          v-else-if="
                            !session.isAccountant && b.status === 'confirmed'
                          "
                          class="row-actions"
                        >
                          <button
                            v-if="canPayStaff(b)"
                            class="text-button"
                            @click="paymentDialog = b"
                          >
                            {{
                              t(
                                isDemo
                                  ? "common.checkout.demoPay"
                                  : "common.payment.title",
                              )
                            }}
                          </button>
                          <button
                            v-if="canCheckIn(b)"
                            class="text-button"
                            :disabled="busy"
                            @click="changeStay(b, 'check-in')"
                          >
                            {{ t("staff.checkIn") }}
                          </button>
                          <button
                            v-if="b.stayStatus === 'in_house'"
                            class="text-button"
                            :disabled="busy"
                            @click="changeStay(b, 'check-out')"
                          >
                            {{ t("staff.checkOut") }}
                          </button>
                          <button
                            v-if="!b.checkedInAt"
                            class="text-button danger"
                            :disabled="busy"
                            @click="prepareCancellation(b)"
                          >
                            {{ t("staff.cancelBooking") }}
                          </button>
                        </div>
                        <span v-else>—</span>
                        <button
                          v-if="
                            b.source === 'staff' &&
                            isBankProvider(b.payment?.provider) &&
                            !canPayStaff(b)
                          "
                          class="text-button"
                          @click="paymentDialog = b"
                        >
                          {{ t("common.payment.details") }}
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div
                v-else-if="section === 'accounts' && filteredAccounts.length"
                class="table-scroll"
                tabindex="0"
                role="region"
                :aria-label="t('staff.dataTable')"
              >
                <table class="workspace-table">
                  <thead>
                    <tr>
                      <th>{{ t("staff.managers") }}</th>
                      <th>{{ t("staff.resort") }}</th>
                      <th>{{ t("staff.access") }}</th>
                      <th>{{ t("staff.action") }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="a in filteredAccounts" :key="a.id">
                      <td :data-label="t('staff.manager')">
                        <strong>{{ a.name }}</strong
                        ><small>{{ a.login }}</small>
                        <small>{{
                          a.role === "admin"
                            ? t("staff.admin")
                            : a.role === "accountant"
                              ? t("common.accounting.role")
                              : t("staff.manager")
                        }}</small>
                      </td>
                      <td :data-label="t('staff.resort')">
                        {{
                          catalog.resorts
                            .filter((r) => String(r.accountId) === a.id)
                            .map((r) => r.name)
                            .join(", ") || "—"
                        }}
                      </td>
                      <td :data-label="t('staff.access')">
                        <span :class="['status-pill', a.status]">{{
                          statusNames[a.status]
                        }}</span>
                      </td>
                      <td :data-label="t('staff.action')">
                        <button
                          class="text-button"
                          v-if="a.role !== 'admin'"
                          @click="open('accounts', a)"
                        >
                          {{ t("staff.configureAccess") }}
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-else-if="section === 'reviews' && filteredReviews.length">
                <article
                  v-for="review in filteredReviews"
                  :key="review.id"
                  class="staff-review"
                >
                  <strong
                    >{{ review.rating }} / 5 ·
                    {{
                      review.status === "pending"
                        ? t("staff.underReview")
                        : review.status === "approved"
                          ? t("staff.published")
                          : t("staff.rejected")
                    }}</strong
                  >
                  <small
                    >{{ timeLabel(review.createdAt) }}
                    {{ t("staff.verifiedStay") }}</small
                  >
                  <p>{{ review.text }}</p>
                  <div class="staff-review-photos">
                    <a
                      v-for="photo in review.photos"
                      :key="photo"
                      :href="photo"
                      target="_blank"
                      rel="noopener noreferrer"
                      ><img
                        :src="photo"
                        :alt="t('staff.guestPhoto')"
                        loading="lazy"
                    /></a>
                  </div>
                  <label class="editor-form"
                    >{{ t("staff.resortReply")
                    }}<textarea
                      v-model="review.reply"
                      maxlength="2000"
                      rows="3"
                    ></textarea>
                  </label>
                  <div class="row-actions">
                    <button
                      class="primary"
                      :disabled="busy"
                      @click="moderateReview(review, 'approved')"
                    >
                      {{ t("staff.publishReview") }}</button
                    ><button
                      class="secondary"
                      :disabled="busy"
                      @click="moderateReview(review, 'rejected')"
                    >
                      {{ t("staff.hideReview") }}
                    </button>
                  </div>
                </article>
              </div>
              <div
                v-else-if="section === 'history' && filteredAudit.length"
                class="audit-list"
              >
                <details v-for="entry in filteredAudit" :key="entry.id">
                  <summary>
                    <span :class="['audit-dot', entry.action]">{{
                      {
                        create: "+",
                        update: "↗",
                        delete: "−",
                        archive: "□",
                        cancel: "×",
                        cancelled: "×",
                        demo_payment: "₸",
                        demo_refund: "↩",
                        "check-in": "↳",
                        "check-out": "↰",
                        payment: "₸",
                        refund: "↶",
                        confirmed: "✓",
                        rejected: "×",
                      }[entry.action]
                    }}</span
                    ><span
                      ><strong
                        >{{
                          {
                            notes: t("staff.board.notesSaved"),
                            create: t("staff.created"),
                            update: t("staff.updated"),
                            delete: t("staff.deleted"),
                            archive: t("staff.archiving"),
                            cancel: t("staff.cancel"),
                            cancelled: t("staff.cancel"),
                            demo_payment: t("staff.demoPayment"),
                            payment_confirmed: t(
                              "common.checkout.paymentBooked",
                            ),
                            payment_expired: t("common.status.expired"),
                            demo_refund: t("staff.demoRefund"),
                            "check-in": t("staff.checkedIn"),
                            "check-out": t("staff.departure"),
                            payment: t("staff.demoPayment"),
                            refund: t("staff.demoRefund"),
                            confirmed: t("staff.approval"),
                            rejected: t("staff.rejection"),
                          }[entry.action]
                        }}
                        · {{ entry.label }}</strong
                      ><small
                        >{{ entry.actor }} · {{ timeLabel(entry.at) }}
                        {{ t("staff.almatySuffix") }}</small
                      ></span
                    ><span class="audit-expand">{{ t("staff.details") }}</span>
                  </summary>
                  <div class="audit-detail">
                    <table class="workspace-table">
                      <thead>
                        <tr>
                          <th>{{ t("staff.field") }}</th>
                          <th>{{ t("staff.before") }}</th>
                          <th>{{ t("staff.after") }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="change in changes(entry)" :key="change.key">
                          <td :data-label="t('staff.field')">
                            {{ fieldNames[change.key] || change.key }}
                          </td>
                          <td :data-label="t('staff.before')">
                            {{ display(change.before) }}
                          </td>
                          <td :data-label="t('staff.after')">
                            {{ display(change.after) }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                    <p v-if="!changes(entry).length" class="field-help">
                      {{ t("staff.noFieldChanges") }}
                    </p>
                  </div>
                </details>
              </div>
              <div v-else class="work-empty">
                <span>⌕</span>
                <h3>
                  {{
                    query || status !== "all"
                      ? t("staff.noResults")
                      : t("staff.noRecords")
                  }}
                </h3>
                <p>
                  {{
                    query || status !== "all"
                      ? t("staff.changeSearch")
                      : t("staff.addFirstRecord")
                  }}
                </p>
                <button
                  v-if="query || status !== 'all'"
                  class="secondary"
                  @click="
                    query = '';
                    status = 'all';
                  "
                >
                  {{ t("staff.resetFilters") }}</button
                ><button v-else-if="canAdd" class="primary" @click="open()">
                  {{ addLabels[section] }}
                </button>
              </div>
              <div class="table-foot">
                {{
                  section === "history"
                    ? t("staff.historyReadOnly")
                    : t("staff.changesTracked")
                }}
                <span v-if="isDemo">{{ t("staff.demoData") }}</span>
              </div>
            </section></template
          ></template
        ></template
      >
    </main></StaffShell
  >
  <StayCard
    ref="stayCard"
    :read-only="session.isAccountant"
    :can-view-history="session.isAdmin"
    v-if="focusedBooking"
    :booking="focusedBooking"
    :audit="audit"
    :busy="busy"
    :error="detailError"
    :can-check-in="canCheckIn(focusedBooking)"
    :can-pay="canPayStaff(focusedBooking)"
    @close="focusedId = null"
    @action="cardAction"
    @notes="saveNotes"
    @saved="load(true)"
  />
  <ResortEditor
    v-if="editor?.kind === 'resorts'"
    :item="editor.item"
    :accounts="accounts"
    @close="editor = null"
    @saved="saved"
  />
  <RoomEditor
    v-if="editor?.kind === 'rooms'"
    :item="editor.item"
    :resort-id="selected"
    @close="editor = null"
    @saved="saved"
  />
  <ClassPricingEditor
    v-if="editor?.kind === 'class-pricing' && current"
    :key="current.id"
    :resort="current"
    @close="editor = null"
    @saved="saved"
  />
  <ChildPolicyEditor
    v-if="editor?.kind === 'child-policy' && current"
    :key="current.id"
    :tariffs="scopedTariffs"
    @close="editor = null"
    @saved="saved"
  />
  <AccountEditor
    v-if="editor?.kind === 'accounts'"
    :item="editor.item"
    :resorts="catalog.resorts"
    @close="editor = null"
    @saved="saved"
  />
  <BookingEditor
    :preset="editor?.preset"
    v-if="editor?.kind === 'bookings' && current"
    staff
    :resort="current"
    :rooms="scopedRooms"
    :tariffs="scopedTariffs"
    @close="editor = null"
    @saved="saved"
  />
  <PaymentDialog
    v-if="paymentDialog"
    :booking="paymentDialog"
    staff
    @close="paymentDialog = null"
    @saved="paymentSaved"
  />
  <Modal
    v-if="confirm"
    :title="confirm.title"
    :busy="busy"
    @close="confirm = null"
    ><p class="confirm-text">{{ confirm.text }}</p>
    <p v-if="confirm.error" class="form-error" role="alert">
      {{ confirm.error }}
    </p>
    <div class="form-actions">
      <button class="secondary" :disabled="busy" @click="confirm = null">
        {{ t("staff.back") }}</button
      ><button
        :class="confirm.target === 'confirmed' ? 'primary' : 'danger-button'"
        :disabled="busy"
        @click="act"
      >
        {{ busy ? t("staff.saving") : t("staff.confirm") }}
      </button>
    </div></Modal
  >
</template>
