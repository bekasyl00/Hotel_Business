<script setup>
import { useWorkspaceBookings } from "../model/use-workspace-bookings.js";
import { useWorkspaceNotifications } from "../model/use-workspace-notifications.js";
import { useWorkspaceFilters } from "../model/use-workspace-filters.js";
import WorkspaceNotifications from "./WorkspaceNotifications.vue";
import WorkspaceResorts from "./WorkspaceResorts.vue";
import WorkspaceRooms from "./WorkspaceRooms.vue";
import WorkspaceBookings from "./WorkspaceBookings.vue";
import WorkspaceAccounts from "./WorkspaceAccounts.vue";
import WorkspaceReviews from "./WorkspaceReviews.vue";
import WorkspaceHistory from "./WorkspaceHistory.vue";
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
import { useBookingStore } from "@/entities/booking";
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
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import {
  enableRequestNotifications,
  staffPushState,
  pendingPushTarget,
  initStaffPushListeners,
  consumePendingPushTarget,
  openSystemNotificationSettings,
} from "@/shared/native";
import { statusNames } from "@/shared/lib";
import { isDemo, isStaffApp } from "@/shared/config";
const { t } = useI18n();
const stayCard = ref(null);
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
  editor = ref(null),
  confirm = ref(null),
  busy = ref(false);
const {
  notifications,
  unreadNotifications,
  loadNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} = useWorkspaceNotifications({ session, selected, error, busy });
const {
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
} = useWorkspaceFilters({
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
});
const {
  paymentDialog,
  bookingView,
  focusedId,
  focusedBooking,
  detailError,
  stayNames,
  canPayStaff,
  paymentSaved,
  createAt,
  cardAction,
  saveNotes,
  canCheckIn,
  changeStay,
  prepareCancellation,
} = useWorkspaceBookings({
  session,
  bookings,
  selected,
  current,
  editor,
  confirm,
  busy,
  error,
  notice,
  load,
  t,
});
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
        <button v-if="section === 'notifications' && !session.isAccountant && ['unknown', 'prompt', 'default'].includes(staffPushState.permission)" class="secondary" @click="enableRequestNotifications">{{ t('staff.notifications.enableLocal') }}</button>
        <div
          v-if="!session.isAccountant && staffPushState.permission === 'denied'"
          class="error-panel"
          role="status"
          data-testid="push-permission-denied"
        >
          <div>
            <strong>{{ t("staff.notifications.pushDeniedTitle") }}</strong>
            <p>{{ t(isStaffApp ? "staff.notifications.pushDeniedBody" : "staff.notifications.browserSettings") }}</p>
          </div>
          <button
            type="button"
            class="secondary"
            v-if="isStaffApp"
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
              <WorkspaceNotifications
                v-if="
                  section === 'notifications' && filteredNotifications.length
                "
                :filtered-notifications="filteredNotifications"
                @read="markNotificationRead"
                @open-booking="openNotificationBooking"
              />
              <WorkspaceResorts
                v-else-if="section === 'resorts' && filteredResorts.length"
                :filtered-resorts="filteredResorts"
                :accounts="accounts"
                :rooms="catalog.rooms"
                :is-admin="session.isAdmin"
                @open="open"
                @confirm="confirm = $event"
                @switch-resort="switchResort"
              />
              <WorkspaceRooms
                v-else-if="section === 'rooms' && filteredRooms.length"
                :filtered-rooms="filteredRooms"
                @open="open"
                @confirm="confirm = $event"
              />
              <WorkspaceBookings
                v-else-if="section === 'bookings' && filteredBookings.length"
                :filtered-bookings="filteredBookings"
                :is-accountant="session.isAccountant"
                :busy="busy"
                :can-pay-staff="canPayStaff"
                :can-check-in="canCheckIn"
                :stay-names="stayNames"
                @focus="focusedId = $event"
                @pay="paymentDialog = $event"
                @cancel="prepareCancellation"
                @stay="changeStay"
              />
              <WorkspaceAccounts
                v-else-if="section === 'accounts' && filteredAccounts.length"
                :filtered-accounts="filteredAccounts"
                :resorts="catalog.resorts"
                @open="open"
              />
              <WorkspaceReviews
                v-else-if="section === 'reviews' && filteredReviews.length"
                :filtered-reviews="filteredReviews"
                :busy="busy"
                @moderate="moderateReview"
              />
              <WorkspaceHistory
                v-else-if="section === 'history' && filteredAudit.length"
                :filtered-audit="filteredAudit"
              />
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
