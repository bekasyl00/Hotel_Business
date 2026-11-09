<script setup>
import { ref, reactive, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { AccountingLedger } from "@/features/accounting-ledger";
import { StaffShell } from "@/widgets/staff-shell";
import { useSessionStore } from "@/entities/session";
import { request, requestFile } from "@/shared/api";
import { isDemo, apiBase } from "@/shared/config";
import { money, dateLabel } from "@/shared/lib";
const { t } = useI18n(),
  router = useRouter(),
  session = useSessionStore();
const data = ref(null),
  error = ref(""),
  busy = ref(false);
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
          <div class="finance-table" tabindex="0">
            <table>
              <thead>
                <tr>
                  <th>{{ t("common.accounting.guest") }}</th>
                  <th>{{ t("staff.resort") }}</th>
                  <th>{{ t("common.accounting.stay") }}</th>
                  <th>{{ t("common.accounting.amount") }}</th>
                  <th>{{ t("common.accounting.payment") }}</th>
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
                </tr>
                <tr v-if="!data.bookings.length">
                  <td colspan="5">{{ t("common.accounting.empty") }}</td>
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
      </template>
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
.finance-table small {
  display: block;
  color: var(--muted);
  margin-top: 6px;
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
