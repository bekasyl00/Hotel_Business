<script setup>
import { ref, reactive, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { DocumentFiles } from "@/shared/ui";
import { AccountingLedger } from "@/features/accounting-ledger";
import { StaffShell } from "@/widgets/staff-shell";
import { useSessionStore } from "@/entities/session";
import { request, requestFile } from "@/shared/api";
import { isDemo, apiBase } from "@/shared/config";
import { money, dateLabel } from "@/shared/lib";
import { Modal } from "@/shared/ui";
const { t } = useI18n(),
  router = useRouter(),
  session = useSessionStore();
const data = ref(null),
  error = ref(""),
  busy = ref(false),
  company = ref(null),
  companyBusy = ref(false),
  companyError = ref("");
const today = new Date().toLocaleDateString("en-CA", {
  timeZone: "Asia/Almaty",
});
const filter = reactive({
  resortId: "",
  paymentMode: isDemo ? "demo" : "production",
  end: today,
  start: today.slice(0, 8) + "01",
  search: "",
  page: 1,
});
let generation = 0;
function query() {
  return new URLSearchParams(filter).toString();
}
async function load(reset = false) {
  if (reset) filter.page = 1;
  const run = ++generation;
  busy.value = true;
  error.value = "";
  try {
    const result = await request("GET", "/accounting?" + query());
    if (run === generation) data.value = result;
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) busy.value = false;
  }
}
async function logout() {
  await session.logout();
  router.push("/staff/login");
}
async function create(bookingId, kind) {
  busy.value = true;
  error.value = "";
  try {
    await request("POST", "/accounting/documents", { bookingId, kind });
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function action(doc, name) {
  busy.value = true;
  error.value = "";
  try {
    await request("POST", `/accounting/documents/${doc.id}/${name}`, {
      version: doc.version,
    });
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function download(path, name, type) {
  error.value = "";
  try {
    const blob = await requestFile(path, apiBase, type);
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    error.value = e.message;
  }
}
async function openCompany() {
  if (!filter.resortId) return;
  companyError.value = "";
  companyBusy.value = true;
  try {
    company.value = {
      supplier: "",
      bin: "",
      address: "",
      iban: "",
      bank: "",
      bik: "",
      director: "",
      accountant: "",
      vatMode: "no_vat",
      vatRate: "0",
      ...(await request("GET", `/accounting/company/${filter.resortId}`)),
    };
  } catch (e) {
    error.value = e.message;
  } finally {
    companyBusy.value = false;
  }
}
async function saveCompany() {
  companyBusy.value = true;
  companyError.value = "";
  try {
    const { resortId, ...body } = company.value;
    await request("PATCH", `/accounting/company/${resortId}`, body);
    company.value = null;
    await load();
  } catch (e) {
    companyError.value = e.message;
  } finally {
    companyBusy.value = false;
  }
}
onMounted(() => load());
</script>
<template>
  <StaffShell section="accounting" @logout="logout"
    ><main class="accounting-page">
      <header class="accounting-heading">
        <div>
          <span class="eyebrow">{{ t("common.accounting.eyebrow") }}</span>
          <h1>{{ t("common.accounting.title") }}</h1>
          <p>{{ t("common.accounting.description") }}</p>
        </div>
        <button
          class="secondary"
          :disabled="isDemo || !filter.resortId || companyBusy"
          @click="openCompany"
        >
          {{ t("common.accounting.company") }}
        </button>
      </header>
      <form class="accounting-filters" @submit.prevent="load(true)">
        <label
          >{{ t("staff.resort")
          }}<select v-model="filter.resortId">
            <option value="">{{ t("common.accounting.all") }}</option>
            <option v-for="r in data?.resorts || []" :key="r.id" :value="r.id">
              {{ r.name }}
            </option>
          </select></label
        >
        <label
          >{{ t("common.accounting.from")
          }}<input v-model="filter.start" type="date" required /></label
        ><label
          >{{ t("common.accounting.to")
          }}<input
            v-model="filter.end"
            type="date"
            :min="filter.start"
            required
        /></label>
        <label
          >{{ t("common.accounting.source")
          }}<select v-model="filter.paymentMode" :disabled="isDemo">
            <option value="production">
              {{ t("common.accounting.production") }}
            </option>
            <option value="sandbox">Halyk sandbox</option>
            <option value="demo">{{ t("common.accounting.demo") }}</option>
          </select></label
        >
        <label
          >{{ t("common.accounting.search")
          }}<input v-model="filter.search" maxlength="100" /></label
        ><button class="primary" :disabled="busy">
          {{ t("common.accounting.apply") }}
        </button>
      </form>
      <p v-if="!filter.resortId" class="field-help">
        {{ t("common.accounting.scopeHint") }}
      </p>
      <p v-if="isDemo" class="field-help">
        {{ t("common.accounting.demoHint") }}
      </p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <p v-if="busy" role="status">{{ t("staff.loadingAccounts") }}</p>
      <template v-if="data"
        ><section class="finance-totals">
          <article v-for="key in ['received', 'refunded', 'net']" :key="key">
            <span>{{ t(`common.accounting.${key}`) }}</span
            ><strong>{{ money(data.totals[key]) }}</strong>
          </article>
        </section>
        <p class="field-help">{{ t("common.accounting.totalsHint") }}</p>
        <AccountingLedger
          :finance="data.finance"
          :resorts="data.resorts"
          :query="query()"
          :payment-mode="filter.paymentMode"
          :resort-id="filter.resortId"
          @saved="load()"
        />
        <section class="finance-section">
          <header>
            <h2>{{ t("common.accounting.bookings") }} · {{ data.count }}</h2>
            <button
              class="secondary"
              :disabled="busy || isDemo"
              @click="
                download(
                  '/accounting/export?' + query(),
                  'accounting.csv',
                  'text/csv',
                )
              "
            >
              {{ t("common.accounting.export") }}
            </button>
          </header>
          <div class="finance-table">
            <table>
              <thead>
                <tr>
                  <th>{{ t("common.accounting.guest") }}</th>
                  <th>{{ t("staff.resort") }}</th>
                  <th>{{ t("common.accounting.stay") }}</th>
                  <th>{{ t("common.accounting.amount") }}</th>
                  <th>{{ t("common.accounting.payment") }}</th>
                  <th>{{ t("common.accounting.prepare") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in data.bookings" :key="b.id">
                  <td>
                    {{ b.guest }}<small>{{ b.id.slice(0, 8) }}</small>
                  </td>
                  <td>
                    {{ b.resort }}<small>{{ b.room }}</small>
                  </td>
                  <td>
                    {{ dateLabel(b.start) }} — {{ dateLabel(b.end)
                    }}<small>{{
                      t(
                        b.completed
                          ? "common.accounting.completed"
                          : "common.accounting.notCompleted",
                      )
                    }}</small>
                  </td>
                  <td>{{ money(b.amount) }}</td>
                  <td>
                    {{
                      b.payment?.status
                        ? t(
                            `common.accounting.paymentStatuses.${b.payment.status}`,
                          )
                        : t("common.accounting.unpaid")
                    }}<small v-if="b.payment?.refundedAmount"
                      >{{ t("common.accounting.refunded") }}:
                      {{ money(b.payment.refundedAmount) }}</small
                    >
                  </td>
                  <td>
                    <div class="document-actions">
                      <button
                        v-for="kind in ['act', 'invoice', 'cash_order']"
                        :key="kind"
                        class="secondary"
                        :disabled="busy || isDemo"
                        @click="create(b.id, kind)"
                      >
                        {{ t(`common.accounting.kinds.${kind}`) }}
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!data.bookings.length">
                  <td colspan="6">{{ t("common.accounting.empty") }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="finance-pagination">
            <button
              class="secondary"
              :disabled="busy || filter.page <= 1"
              @click="
                filter.page--;
                load();
              "
            >
              {{ t("common.gallery.previous") }}</button
            ><span>{{ filter.page }}</span
            ><button
              class="secondary"
              :disabled="busy || filter.page * 50 >= data.count"
              @click="
                filter.page++;
                load();
              "
            >
              {{ t("common.gallery.next") }}
            </button>
          </div>
        </section>
        <section class="finance-section">
          <header>
            <h2>
              {{ t("common.accounting.documents") }} · {{ data.documentCount }}
            </h2>
          </header>
          <p class="field-help">{{ t("common.accounting.documentHint") }}</p>
          <div class="document-grid">
            <article
              v-for="doc in data.documents"
              :key="doc.id"
              class="document-card"
            >
              <span :class="['document-state', doc.state]">{{
                t(`common.accounting.states.${doc.state}`)
              }}</span>
              <h3>{{ t(`common.accounting.kinds.${doc.kind}`) }}</h3>
              <p>{{ doc.number }} · {{ doc.guest }}</p>
              <strong>{{ money(doc.amount) }}</strong
              ><small>{{
                t(
                  `common.accounting.${doc.paymentMode === "sandbox" ? "sandbox" : doc.paymentMode === "production" ? "production" : doc.paymentMode === "demo" ? "demo" : "unpaid"}`,
                )
              }}</small>
              <div class="document-actions">
                <DocumentFiles
                  :path="`/accounting/documents/${doc.id}`"
                  :number="doc.number"
                />
                <button
                  v-if="doc.state === 'draft'"
                  class="secondary"
                  :disabled="busy"
                  @click="action(doc, 'refresh')"
                >
                  {{ t("common.accounting.refresh") }}</button
                ><button
                  v-if="doc.state === 'draft' && doc.kind !== 'cash_order'"
                  class="primary"
                  :disabled="busy"
                  @click="action(doc, 'release')"
                >
                  {{ t("common.accounting.release") }}</button
                ><button
                  v-if="doc.state !== 'voided'"
                  class="text-button danger"
                  :disabled="busy"
                  @click="action(doc, 'void')"
                >
                  {{ t("common.accounting.void") }}
                </button>
              </div>
            </article>
            <p v-if="!data.documents.length">
              {{ t("common.accounting.empty") }}
            </p>
          </div>
          <p v-if="data.documentCount > 200" class="field-help">
            {{ t("common.accounting.documentLimit") }}
          </p>
        </section>
      </template>
      <Modal
        v-if="company"
        :title="t('common.accounting.company')"
        wide
        :busy="companyBusy"
        @close="company = null"
        ><form class="editor-form" @submit.prevent="saveCompany">
          <div class="form-grid">
            <label
              v-for="key in [
                'supplier',
                'bin',
                'address',
                'iban',
                'bank',
                'bik',
                'director',
                'accountant',
              ]"
              :key="key"
              >{{ t(`common.accounting.fields.${key}`)
              }}<input
                v-model="company[key]"
                :required="['supplier', 'bin', 'address'].includes(key)"
                :maxlength="
                  key === 'bin' ? 12 : key === 'address' ? 240 : 160
                " /></label
            ><label
              >{{ t("common.accounting.vat")
              }}<select
                v-model="company.vatMode"
                @change="
                  company.vatRate =
                    company.vatMode === 'no_vat' ? '0' : company.vatRate
                "
              >
                <option value="no_vat">
                  {{ t("common.accounting.noVat") }}
                </option>
                <option value="included">
                  {{ t("common.accounting.vatIncluded") }}
                </option>
              </select></label
            ><label v-if="company.vatMode === 'included'"
              >{{ t("common.accounting.vatRate")
              }}<input
                v-model="company.vatRate"
                type="number"
                min="0.01"
                max="100"
                step="0.01"
                required
            /></label>
          </div>
          <p class="field-help">{{ t("common.accounting.companyHint") }}</p>
          <p v-if="companyError" class="form-error" role="alert">
            {{ companyError }}
          </p>
          <button class="primary" :disabled="companyBusy">
            {{ t("staff.saveAccess") }}
          </button>
        </form></Modal
      >
    </main></StaffShell
  >
</template>
<style scoped>
.accounting-page {
  padding: 32px;
  min-width: 0;
  max-width: 1600px;
  margin: auto;
}
.accounting-heading,
.finance-section > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.accounting-heading h1 {
  font-size: 34px;
  margin: 8px 0;
}
.accounting-heading p {
  max-width: 680px;
  color: var(--muted);
}
.accounting-filters {
  display: flex;
  align-items: end;
  flex-wrap: wrap;
  gap: 12px;
  margin: 26px 0 10px;
}
.accounting-filters label {
  display: grid;
  gap: 7px;
  font-size: 13px;
  flex: 1;
  min-width: 140px;
}
.accounting-filters input,
.accounting-filters select {
  min-height: 44px;
  width: 100%;
  border: 1px solid var(--line, #dfe4dc);
  border-radius: 8px;
  background: #fff;
  padding: 10px;
  color: inherit;
}
.finance-totals {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 24px;
}
.finance-totals article {
  background: white;
  border: 1px solid #dde5dc;
  border-radius: 14px;
  padding: 24px;
  display: grid;
  gap: 12px;
}
.finance-totals strong {
  font-size: 28px;
}
.finance-section {
  margin: 32px 0;
}
.finance-table {
  overflow: auto;
  background: white;
  border-radius: 12px;
  border: 1px solid #dde5dc;
}
.finance-table table {
  border-collapse: collapse;
  width: 100%;
  min-width: 800px;
}
.finance-table th,
.finance-table td {
  text-align: left;
  padding: 16px 12px;
  border-bottom: 1px solid #e7ece6;
  vertical-align: top;
  font-size: 13px;
}
.finance-table th {
  background: #f3f6f1;
  color: #405b4e;
}
.finance-table small,
.document-card small {
  display: block;
  color: var(--muted);
  margin-top: 6px;
}
.document-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.document-actions button {
  min-height: 44px;
}
.document-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: 16px;
}
.document-card {
  border: 1px solid #dfe6dc;
  border-radius: 14px;
  padding: 20px;
  background: white;
}
.document-state {
  display: inline-block;
  padding: 5px 9px;
  border-radius: 6px;
  background: #f7edcf;
  font-size: 12px;
}
.document-state.released {
  background: #dcf1e5;
}
.document-state.voided {
  background: #f5dddd;
}
.finance-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 16px;
  margin-top: 16px;
}
@media (max-width: 760px) {
  .accounting-page {
    padding: 18px 14px;
  }
  .finance-totals {
    grid-template-columns: 1fr;
    gap: 10px;
  }
  .finance-totals article {
    padding: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .finance-totals strong {
    font-size: 22px;
  }
  .accounting-heading h1 {
    font-size: 28px;
  }
}
</style>
