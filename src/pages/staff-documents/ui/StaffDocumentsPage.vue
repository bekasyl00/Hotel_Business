<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { StaffShell } from "@/widgets/staff-shell";
import { DocumentGuests } from "@/features/document-guests";
import { BookingDocuments } from "@/features/booking-documents";
import { propertyToday } from "@/entities/booking";
import { useSessionStore } from "@/entities/session";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
import { dateLabel } from "@/shared/lib";
import { Modal } from "@/shared/ui";
const { t } = useI18n(),
  router = useRouter(),
  session = useSessionStore();
const data = ref(null),
  error = ref(""),
  loading = ref(false),
  selected = ref(null),
  editor = ref(null),
  rosterBusy = ref(false),
  rosterDirty = ref(false),
  documentsBusy = ref(false),
  revision = ref(0);
const today = propertyToday("Asia/Almaty");
const filter = reactive({
  resortId: "",
  start: today.slice(0, 8) + "01",
  end: today,
  paymentMode: "production",
  search: "",
  page: 1,
});
let generation = 0;
async function load(reset = false) {
  if (reset) filter.page = 1;
  const run = ++generation;
  loading.value = true;
  error.value = "";
  try {
    if (!isDemo) {
      const result = await request(
        "GET",
        "/accounting/documents?" + new URLSearchParams(filter),
      );
      if (run === generation) data.value = result;
    }
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
function open(booking) {
  selected.value = booking;
  revision.value = 0;
}
function close() {
  if (!editor.value || editor.value.canLeave()) selected.value = null;
}
async function logout() {
  if (
    rosterBusy.value ||
    documentsBusy.value ||
    (editor.value && !editor.value.canLeave())
  )
    return;
  selected.value = null;
  await nextTick();
  try {
    await session.logout();
    await router.replace("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
onMounted(() => load());
onBeforeUnmount(() => generation++);
</script>
<template>
  <StaffShell section="documents" @logout="logout">
    <main class="staff-documents-page">
      <header class="documents-heading">
        <div>
          <span class="eyebrow">{{ t("staff.workspaceEyebrow") }}</span>
          <h1>{{ t("common.staffDocuments.title") }}</h1>
          <p>{{ t("common.staffDocuments.description") }}</p>
        </div>
        <RouterLink class="secondary" to="/staff/profile">{{
          t("common.staffProfile.companyTitle")
        }}</RouterLink>
      </header>
      <p v-if="isDemo" class="field-help">
        {{ t("common.accounting.demoHint") }}
      </p>
      <template v-else>
        <form class="documents-filters" @submit.prevent="load(true)">
          <label
            >{{ t("staff.resort")
            }}<select v-model="filter.resortId">
              <option value="">{{ t("common.accounting.all") }}</option>
              <option
                v-for="resort in data?.resorts || []"
                :key="resort.id"
                :value="resort.id"
              >
                {{ resort.name }}
              </option>
            </select></label
          >
          <label
            >{{ t("common.accounting.from")
            }}<input v-model="filter.start" type="date" required
          /></label>
          <label
            >{{ t("common.accounting.to")
            }}<input
              v-model="filter.end"
              type="date"
              :min="filter.start"
              required
          /></label>
          <label
            >{{ t("common.accounting.source")
            }}<select v-model="filter.paymentMode">
              <option value="production">
                {{ t("common.accounting.production") }}
              </option>
              <option value="sandbox">
                {{ t("common.accounting.sandbox") }}
              </option>
              <option value="demo">{{ t("common.accounting.demo") }}</option>
            </select></label
          >
          <label
            >{{ t("common.accounting.search")
            }}<input v-model="filter.search" maxlength="100"
          /></label>
          <button class="primary" :disabled="loading">
            {{ t("common.accounting.apply") }}
          </button>
        </form>
        <p class="field-help">{{ t("common.staffDocuments.filterHelp") }}</p>
        <p v-if="error" role="alert" class="form-error">{{ error }}</p>
        <p v-if="loading" role="status">
          {{ t("common.staffDocuments.loading") }}
        </p>
        <section v-if="data" :aria-busy="loading">
          <h2>
            {{ t("common.staffDocuments.bookings", { count: data.count }) }}
          </h2>
          <div
            class="documents-table"
            tabindex="0"
            :aria-label="t('common.staffDocuments.title')"
          >
            <table>
              <thead>
                <tr>
                  <th>{{ t("common.accounting.guest") }}</th>
                  <th>{{ t("staff.resort") }}</th>
                  <th>{{ t("common.accounting.stay") }}</th>
                  <th>{{ t("common.accounting.documents") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="booking in data.bookings" :key="booking.id">
                  <td>
                    {{ booking.guest
                    }}<small>{{
                      t("common.documentGuests.booking", {
                        id: booking.id.slice(0, 8),
                      })
                    }}</small>
                  </td>
                  <td>
                    {{ booking.resort }}<small>{{ booking.room }}</small>
                  </td>
                  <td>
                    {{ dateLabel(booking.start) }} — {{ dateLabel(booking.end)
                    }}<small>{{
                      t(
                        booking.checkedOutAt
                          ? "common.accounting.completed"
                          : "common.accounting.notCompleted",
                      )
                    }}</small>
                  </td>
                  <td>
                    <button class="secondary" @click="open(booking)">
                      {{ t("common.staffDocuments.openBooking") }}
                    </button>
                  </td>
                </tr>
                <tr v-if="!data.bookings.length">
                  <td colspan="4">{{ t("common.accounting.empty") }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="documents-pagination">
            <button
              class="secondary"
              :disabled="loading || filter.page <= 1"
              @click="
                filter.page--;
                load();
              "
            >
              {{ t("common.gallery.previous") }}</button
            ><span>{{ filter.page }}</span
            ><button
              class="secondary"
              :disabled="loading || filter.page * 50 >= data.count"
              @click="
                filter.page++;
                load();
              "
            >
              {{ t("common.gallery.next") }}
            </button>
          </div>
        </section>
      </template>
      <Modal
        v-if="selected"
        wide
        :title="t('common.staffDocuments.bookingTitle')"
        :busy="rosterBusy || documentsBusy"
        @close="close"
      >
        <div class="selected-booking">
          <h3>{{ selected.guest }}</h3>
          <p>{{ selected.resort }} · {{ selected.room }}</p>
          <p>{{ dateLabel(selected.start) }} — {{ dateLabel(selected.end) }}</p>
        </div>
        <DocumentGuests
          ref="editor"
          :disabled="documentsBusy"
          :booking-id="selected.id"
          :guest-name="selected.guest"
          @busy="rosterBusy = $event"
          @dirty="rosterDirty = $event"
          @saved="revision++"
        />
        <BookingDocuments
          :booking-id="selected.id"
          :completed="Boolean(selected.checkedOutAt)"
          :revision="revision"
          manage
          :blocked="rosterDirty || rosterBusy"
          @busy="documentsBusy = $event"
        />
      </Modal>
    </main>
  </StaffShell>
</template>
<style scoped>
.staff-documents-page {
  max-width: 1500px;
  min-width: 0;
  margin: auto;
  padding: 32px;
}
.documents-heading,
.documents-pagination {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.documents-heading h1 {
  font-size: clamp(26px, 4vw, 34px);
  margin: 8px 0;
}
.documents-heading p {
  max-width: 740px;
  color: var(--muted);
  line-height: 1.5;
}
.documents-heading a {
  text-decoration: none;
  text-align: center;
}
.documents-filters {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 12px;
  margin: 24px 0 8px;
}
.documents-filters label {
  display: grid;
  gap: 7px;
  font-size: 13px;
  flex: 1;
  min-width: 140px;
}
.documents-filters input,
.documents-filters select {
  min-height: 44px;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--line, #dfe4dc);
  border-radius: 8px;
  background: #fff;
  color: inherit;
  padding: 10px;
}
.documents-table {
  overflow: auto;
  border: 1px solid var(--line, #dfe4dc);
  border-radius: 14px;
  background: white;
}
table {
  border-collapse: collapse;
  width: 100%;
  min-width: 700px;
}
th,
td {
  padding: 16px;
  border-bottom: 1px solid #edf0eb;
  text-align: left;
}
th {
  background: #f4f6ef;
  font-size: 13px;
}
td {
  font-size: 14px;
}
td small {
  display: block;
  color: var(--muted);
  margin-top: 6px;
}
.documents-table button {
  font-size: 14px;
  padding: 10px 14px;
  min-height: 44px;
}
.documents-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
.selected-booking h3 {
  margin: 0 0 8px;
}
.selected-booking p {
  margin: 5px 0;
  color: var(--muted);
}
@media (max-width: 760px) {
  .staff-documents-page {
    padding: 18px 14px;
  }
  .documents-heading a {
    width: 100%;
  }
  .documents-filters label {
    flex-basis: 44%;
    min-width: 0;
  }
  .documents-filters > button {
    width: 100%;
  }
}
</style>
