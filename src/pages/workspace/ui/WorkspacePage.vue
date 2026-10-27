<script setup>
import { useI18n } from "vue-i18n";
import { computed, ref, watch, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "@/entities/session";
import { useResortStore } from "@/entities/resort";
import { useBookingStore } from "@/entities/booking";
import { StaffShell } from "@/widgets/staff-shell";
import { Overview } from "@/widgets/overview";
import { ResortEditor } from "@/features/edit-resort";
import { RoomEditor } from "@/features/edit-room";
import { TariffEditor } from "@/features/edit-tariff";
import { AccountEditor } from "@/features/edit-account";
import { BookingEditor } from "@/features/create-booking";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { money, dateLabel, timeLabel, statusNames } from "@/shared/lib";
import { isDemo, isStaffApp } from "@/shared/config";
const { t } = useI18n();
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
  tariffs: t("staff.tariffsServices"),
  bookings: t("staff.bookings"),
  reviews: t("staff.guestReviews"),
  history: t("staff.history"),
  accounts: t("staff.managers"),
}));
const subtitles = computed(() => ({
  overview: t("staff.overviewSubtitle"),
  resorts: t("staff.resortsSubtitle"),
  rooms: t("staff.roomsSubtitle"),
  tariffs: t("staff.tariffsSubtitle"),
  bookings: t("staff.bookingsSubtitle"),
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
  editor = ref(null),
  confirm = ref(null),
  busy = ref(false);
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
const filteredTariffs = computed(() =>
  scopedTariffs.value
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
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: current.value?.timeZone || "Asia/Almaty",
  }).format(new Date());
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
    await load();
  } catch (e) {
    error.value = e.message;
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
    await load();
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
const canAdd = computed(() =>
  ["resorts", "accounts"].includes(section.value)
    ? session.isAdmin
    : ["rooms", "tariffs", "bookings"].includes(section.value) &&
      current.value &&
      current.value.status !== "archived",
);
const addLabels = computed(() => ({
  resorts: t("staff.createResort"),
  rooms: t("staff.addRoom"),
  tariffs: t("staff.addTariff"),
  bookings: t("staff.addBooking"),
  accounts: t("staff.addManager"),
}));
let generation = 0;
async function load() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  try {
    await session.restore();
    if (!session.user) return router.replace("/staff/login");
    const data = await request("GET", "/workspace");
    if (run !== generation) return;
    catalog.setData(data);
    bookings.items = data.bookings;
    accounts.value = data.accounts;
    audit.value = data.audit;
    reviews.value = data.reviews || [];
    if (!catalog.resorts.some((r) => r.id === selected.value))
      selected.value =
        catalog.resorts.find((r) => r.status !== "archived")?.id ||
        catalog.resorts[0]?.id ||
        "";
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function logout() {
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
  await load();
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
    await load();
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
watch(section, () => {
  query.value = "";
  status.value = "all";
  editor.value = null;
});
const storageChanged = (e) => {
  if (e.key === "tynys:workspace:v2") load();
};
onMounted(() => {
  load();
  window.addEventListener("storage", storageChanged);
});
onBeforeUnmount(() => {
  generation++;
  window.removeEventListener("storage", storageChanged);
});
</script>
<template>
  <StaffShell :section="section" @logout="logout"
    ><main class="work-main">
      <div v-if="isDemo" class="demo-strip">
        <span class="demo-dot"></span
        >{{
          t(isStaffApp ? "common.mobile.demoWorkspace" : "staff.demoWorkspace")
        }}
      </div>
      <div
        v-if="!titles[section] || (section === 'accounts' && !session.isAdmin)"
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
              ['rooms', 'tariffs', 'bookings', 'reviews', 'history'].includes(
                section,
              )
            "
            class="context-bar"
          >
            <label
              >{{ t("staff.resort")
              }}<select v-model="selected" :disabled="!session.isAdmin">
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
              t("staff.contextCount", {
                rooms: scopedRooms.length,
                tariffs: scopedTariffs.length,
              })
            }}</span>
          </div>
          <Overview
            v-if="section === 'overview'"
            :resorts="catalog.resorts"
            :rooms="catalog.rooms"
            :bookings="bookings.items"
            @bookings="router.push('/staff/bookings')"
            @create="current ? open('bookings') : router.push('/staff/resorts')"
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
                ><select v-model="status" :aria-label="t('staff.recordStatus')">
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
                    <option value="approved">{{ t("staff.published") }}</option>
                    <option value="rejected">
                      {{ t("staff.rejected") }}
                    </option></template
                  ><template v-else
                    ><option value="active">{{ t("staff.active") }}</option>
                    <option
                      :value="section === 'rooms' ? 'maintenance' : 'disabled'"
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
                class="text-button"
                @click="load"
                :aria-label="t('staff.refreshData')"
              >
                {{ t("staff.refresh") }}
              </button>
            </div>
            <div
              v-if="section === 'resorts' && filteredResorts.length"
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
                      ><small>{{ r.area }} {{ t("staff.squareMetres") }}</small>
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
              v-else-if="section === 'tariffs' && filteredTariffs.length"
              class="table-scroll"
              tabindex="0"
              role="region"
              :aria-label="t('staff.dataTable')"
            >
              <table class="workspace-table">
                <thead>
                  <tr>
                    <th>{{ t("staff.tariff") }}</th>
                    <th>{{ t("staff.included") }}</th>
                    <th>{{ t("staff.supplementPerGuestNight") }}</th>
                    <th>{{ t("staff.status") }}</th>
                    <th>{{ t("staff.actions") }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="tariff in filteredTariffs" :key="tariff.id">
                    <td :data-label="t('staff.tariff')">
                      <strong>{{ tariff.name }}</strong
                      ><small v-if="tariff.priceKind === 'discount'">{{
                        t("staff.discountBadge", {
                          percent: tariff.discountPercent,
                        })
                      }}</small
                      ><small>{{ tariff.description }}</small>
                    </td>
                    <td :data-label="t('staff.included')">
                      {{ tariff.features.join(" · ") || "—" }}
                    </td>
                    <td
                      :data-label="t('staff.supplementPerGuestNight')"
                      class="numeric"
                    >
                      {{ money(tariff.supplement) }}
                    </td>
                    <td :data-label="t('staff.status')">
                      <span :class="['status-pill', tariff.status]">{{
                        statusNames[tariff.status]
                      }}</span>
                    </td>
                    <td :data-label="t('staff.actions')">
                      <div class="row-actions">
                        <button
                          class="text-button"
                          @click="open('tariffs', tariff)"
                        >
                          {{ t("staff.edit") }}</button
                        ><button
                          class="text-button danger"
                          @click="
                            confirm = {
                              kind: 'tariffs',
                              item: tariff,
                              title: t('staff.deleteTariffTitle', {
                                name: tariff.name,
                              }),
                              text: t('staff.deleteTariffText'),
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
                    <th>{{ t("staff.roomTariff") }}</th>
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
                        v-if="b.guestProfileId"
                        :to="`/staff/guests/${b.guestProfileId}`"
                        ><strong>{{ b.guestLabel }}</strong></RouterLink
                      >
                      <strong v-else>{{ b.guestLabel }}</strong
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
                    <td :data-label="t('staff.roomTariff')">
                      № {{ b.unit }} · {{ b.roomName
                      }}<small
                        >{{ b.tariffName }} ·
                        {{ t("staff.guestCount", { count: b.guests }) }}</small
                      >
                    </td>
                    <td :data-label="t('staff.dates')">
                      {{ dateLabel(b.start)
                      }}<small>{{
                        t("staff.untilDate", { date: dateLabel(b.end) })
                      }}</small>
                    </td>
                    <td :data-label="t('staff.amount')" class="numeric">
                      {{ money(b.total)
                      }}<small v-if="b.payment"
                        >{{
                          b.payment.status === "paid"
                            ? t("staff.demoPaid")
                            : b.payment.status === "failed"
                              ? t("staff.demoFailed")
                              : t("staff.demoRefunded")
                        }}<span v-if="b.payment.refundedAmount">
                          {{ money(b.payment.refundedAmount) }}</span
                        ></small
                      >
                      <RouterLink
                        v-if="b.payment?.receiptUrl"
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
                      <small v-if="b.checkedInAt">{{
                        t("staff.arrivalAt", { date: timeLabel(b.checkedInAt) })
                      }}</small>
                      <small v-if="b.checkedOutAt">{{
                        t("staff.departureAt", {
                          date: timeLabel(b.checkedOutAt),
                        })
                      }}</small>
                    </td>
                    <td :data-label="t('staff.action')">
                      <div v-if="b.status === 'pending'" class="row-actions">
                        <button
                          class="text-button"
                          @click="
                            confirm = {
                              kind: 'bookings',
                              item: b,
                              target: 'confirmed',
                              title: t('staff.approveBookingTitle'),
                              text: t('staff.approveBookingText'),
                            }
                          "
                        >
                          {{ t("staff.confirm") }}
                        </button>
                        <button
                          class="text-button danger"
                          @click="
                            confirm = {
                              kind: 'bookings',
                              item: b,
                              target: 'rejected',
                              title: t('staff.rejectBookingTitle'),
                              text: t('staff.rejectBookingText'),
                            }
                          "
                        >
                          {{ t("staff.reject") }}
                        </button>
                      </div>
                      <div
                        v-else-if="b.status === 'confirmed'"
                        class="row-actions"
                      >
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
                    <th>{{ t("staff.manager") }}</th>
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
                    </td>
                    <td :data-label="t('staff.resort')">
                      {{
                        catalog.resorts.find((r) => r.id === a.resortId)
                          ?.name || "—"
                      }}
                    </td>
                    <td :data-label="t('staff.access')">
                      <span :class="['status-pill', a.status]">{{
                        statusNames[a.status]
                      }}</span>
                    </td>
                    <td :data-label="t('staff.action')">
                      <button class="text-button" @click="open('accounts', a)">
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
                          create: t("staff.created"),
                          update: t("staff.updated"),
                          delete: t("staff.deleted"),
                          archive: t("staff.archiving"),
                          cancel: t("staff.cancel"),
                          cancelled: t("staff.cancel"),
                          demo_payment: t("staff.demoPayment"),
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
      >
    </main></StaffShell
  >
  <ResortEditor
    v-if="editor?.kind === 'resorts'"
    :item="editor.item"
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
  <TariffEditor
    v-if="editor?.kind === 'tariffs'"
    :item="editor.item"
    :resort-id="selected"
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
    v-if="editor?.kind === 'bookings' && current"
    staff
    :resort="current"
    :rooms="scopedRooms"
    :tariffs="scopedTariffs"
    @close="editor = null"
    @saved="saved"
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
