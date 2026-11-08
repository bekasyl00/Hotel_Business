<script setup>
import { ref, reactive, onBeforeUnmount, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { request, requestFile } from "@/shared/api";
import { apiBase, isDemo } from "@/shared/config";
import { Modal } from "@/shared/ui";
import { money } from "@/shared/lib";
const props = defineProps({
  finance: Object,
  resorts: Array,
  query: String,
  paymentMode: String,
  resortId: String,
});
const emit = defineEmits(["saved"]);
const { t } = useI18n();
const open = ref(false),
  busy = ref(false),
  error = ref(""),
  voiding = ref(null),
  reason = ref(""),
  report = ref(""),
  saveLink = ref(null);
const categories = [
  "bank_fee",
  "operations",
  "marketing",
  "payroll",
  "taxes",
  "other",
];
const metrics = [
  "confirmedAmount",
  "awaitingPayment",
  "confirmedUnpaid",
  "commissionEstimate",
];
const form = reactive({
  resortId: null,
  date: "",
  amount: "",
  category: "operations",
  description: "",
});
let attempt,
  active = true;
function create() {
  Object.assign(form, {
    resortId: props.resortId || null,
    date: new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Almaty" }),
    amount: "",
    category: "operations",
    description: "",
  });
  error.value = "";
  attempt = null;
  open.value = true;
}
async function save() {
  busy.value = true;
  error.value = "";
  try {
    const payload = {
      ...form,
      resortId: form.resortId || null,
      amount: Number(form.amount),
      paymentMode: props.paymentMode,
    };
    const fingerprint = JSON.stringify(payload);
    if (attempt?.fingerprint !== fingerprint)
      attempt = { fingerprint, id: crypto.randomUUID() };
    await request("POST", "/accounting/expenses", {
      ...payload,
      requestId: attempt.id,
    });
    open.value = false;
    emit("saved");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function cancelExpense() {
  busy.value = true;
  error.value = "";
  try {
    await request("POST", `/accounting/expenses/${voiding.value.id}/void`, {
      version: voiding.value.version,
      reason: reason.value,
    });
    voiding.value = null;
    emit("saved");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function exportReport() {
  busy.value = true;
  error.value = "";
  try {
    const blob = await requestFile(
      "/accounting/report.xlsx?" + props.query,
      apiBase,
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    if (!active) return;
    if (report.value) URL.revokeObjectURL(report.value);
    report.value = URL.createObjectURL(blob);
    await nextTick();
    saveLink.value?.click();
  } catch (e) {
    if (active) error.value = e.message;
  } finally {
    if (active) busy.value = false;
  }
}
onBeforeUnmount(() => {
  active = false;
  if (report.value) URL.revokeObjectURL(report.value);
});
</script>
<template>
  <section v-if="finance" class="ledger">
    <header>
      <h2>{{ t("common.finance.title") }}</h2>
      <button
        class="secondary"
        :disabled="busy || isDemo"
        @click="exportReport"
      >
        {{ t("common.finance.export") }}
      </button>
    </header>
    <p class="field-help">{{ t("common.finance.basis") }}</p>
    <p v-if="error && !open && !voiding" class="form-error" role="alert">
      {{ error }}
    </p>
    <p v-if="report" role="status">
      {{ t("common.accounting.fileReady") }}
      <a ref="saveLink" :href="report" download="tynys-finance.xlsx">{{
        t("common.accounting.downloadFile", { format: "XLSX" })
      }}</a>
    </p>
    <div class="metrics">
      <article v-for="key in metrics" :key="key">
        <span>{{ t(`common.finance.${key}`) }}</span
        ><strong>{{ money(finance.totals[key]) }}</strong>
      </article>
    </div>
    <p>
      {{
        t("common.finance.unconfigured", {
          count: finance.totals.unconfiguredCommissionCount,
        })
      }}
    </p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{{ t("staff.resort") }}</th>
            <th
              v-for="key in ['received', 'refunded', 'net', 'expenses']"
              :key="key"
            >
              {{ t(`common.finance.${key}`) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in finance.byResort" :key="row.resortId">
            <th>{{ row.name }}</th>
            <td
              v-for="key in ['received', 'refunded', 'net', 'expenses']"
              :key="key"
            >
              {{ money(row[key]) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="finance.resortsTruncated">{{ t("common.finance.limit") }}</p>
    <header>
      <h2>
        {{ t("common.finance.expenses") }} ·
        {{ money(finance.totals.expenses) }}
      </h2>
      <button class="primary" :disabled="busy || isDemo" @click="create">
        {{ t("common.finance.addExpense") }}
      </button>
    </header>
    <p>
      {{ t("common.finance.platformExpenses") }}:
      {{ money(finance.platformExpenses) }}
    </p>
    <p class="field-help">{{ t("common.finance.expenseHint") }}</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{{ t("common.finance.date") }}</th>
            <th>{{ t("common.finance.category") }}</th>
            <th>{{ t("staff.resort") }}</th>
            <th>{{ t("common.finance.description") }}</th>
            <th>{{ t("common.accounting.amount") }}</th>
            <th>{{ t("staff.status") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in finance.expenses" :key="item.id">
            <td>{{ item.date }}</td>
            <td>{{ t(`common.finance.categories.${item.category}`) }}</td>
            <td>
              {{
                resorts.find((r) => r.id === item.resortId)?.name ||
                t("staff.platform")
              }}
            </td>
            <td>{{ item.description }}</td>
            <td>{{ money(item.amount) }}</td>
            <td>
              <span v-if="item.voidedAt"
                >{{ t("common.accounting.states.voided") }}:
                {{ item.voidReason }}</span
              ><button
                v-else
                class="text-button danger"
                @click="
                  voiding = item;
                  reason = '';
                  error = '';
                "
              >
                {{ t("common.finance.voidExpense") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!finance.expenses.length">{{ t("common.finance.empty") }}</p>
    <p v-if="finance.expenseCount > 200">{{ t("common.finance.limit") }}</p>
    <Modal
      v-if="open"
      :title="t('common.finance.addExpense')"
      :busy="busy"
      @close="open = false"
      ><form class="editor-form" @submit.prevent="save">
        <label
          >{{ t("staff.resort")
          }}<select v-model="form.resortId">
            <option :value="null">{{ t("staff.platform") }}</option>
            <option v-for="r in resorts" :key="r.id" :value="r.id">
              {{ r.name }}
            </option>
          </select></label
        >
        <label
          >{{ t("common.finance.date")
          }}<input v-model="form.date" type="date" required
        /></label>
        <label
          >{{ t("common.accounting.amount") }} KZT<input
            v-model="form.amount"
            type="number"
            min="1"
            max="1000000000000"
            step="1"
            required
        /></label>
        <label
          >{{ t("common.finance.category")
          }}<select v-model="form.category">
            <option v-for="key in categories" :key="key" :value="key">
              {{ t(`common.finance.categories.${key}`) }}
            </option>
          </select></label
        >
        <label
          >{{ t("common.finance.description")
          }}<input v-model="form.description" required maxlength="240"
        /></label>
        <p>{{ t(`common.accounting.${paymentMode}`) }}</p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="primary" :disabled="busy">
          {{ t("common.finance.save") }}
        </button>
      </form></Modal
    >
    <Modal
      v-if="voiding"
      :title="t('common.finance.voidExpense')"
      :busy="busy"
      @close="voiding = null"
      ><form class="editor-form" @submit.prevent="cancelExpense">
        <label
          >{{ t("common.finance.reason")
          }}<textarea v-model="reason" required minlength="3" maxlength="240" />
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="primary" :disabled="busy">
          {{ t("common.finance.voidExpense") }}
        </button>
      </form></Modal
    >
  </section>
</template>
<style scoped>
.ledger {
  margin: 28px 0;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 24px;
}
h2 {
  margin: 0;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin: 20px 0;
}
.metrics article {
  padding: 18px;
  border: 1px solid #dce5dc;
  border-radius: 12px;
  background: #fff;
}
.metrics span {
  display: block;
  color: var(--muted);
  font-size: 14px;
}
.metrics strong {
  display: block;
  font-size: 24px;
  margin-top: 8px;
}
.table-wrap {
  overflow: auto;
  max-width: 100%;
  margin: 16px 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 640px;
}
th,
td {
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid #dde5dc;
}
td {
  max-width: 260px;
  overflow-wrap: anywhere;
}
a {
  color: var(--forest, #244e3e);
  text-decoration: underline;
}
</style>
