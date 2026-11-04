<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { money } from "@/shared/lib";
const props = defineProps({
  booking: { type: Object, required: true },
  staff: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const { t, locale } = useI18n();
const payment = ref(null),
  busy = ref(false),
  error = ref(""),
  paused = ref(false);
const now = ref(Date.now());
const prefix = props.staff ? "/payments/staff" : "/payments";
const requestKey = crypto.randomUUID();
let stopped = false,
  timer,
  clock,
  polls = 0,
  notified = props.booking.payment?.checkoutStatus === "succeeded";
const expires = computed(() =>
  Date.parse(payment.value?.expiresAt || props.booking.holdExpiresAt || ""),
);
const remaining = computed(() =>
  Math.max(0, Math.ceil((expires.value - now.value) / 60000)),
);
const terminal = computed(() =>
  ["succeeded", "expired", "reconciliation_required"].includes(
    payment.value?.status,
  ),
);
const safeUrl = computed(() => {
  if (!payment.value?.checkoutUrl || remaining.value <= 0) return null;
  try {
    const url = new URL(payment.value.checkoutUrl);
    return url.protocol === "https:" &&
      url.host === "testepay.homebank.kz" &&
      /^\/api\/redirect\/invoice-link\/[a-f0-9-]{36}$/i.test(url.pathname) &&
      !url.search &&
      !url.hash
      ? url.href
      : null;
  } catch {
    return null;
  }
});
function schedule() {
  clearTimeout(timer);
  if (stopped || terminal.value || !payment.value || polls >= 35) {
    paused.value = polls >= 35;
    return;
  }
  timer = setTimeout(read, Math.min(2000 + polls * 1000, 10000));
}
async function read() {
  if (stopped || !payment.value) return;
  try {
    const result = await request("GET", `${prefix}/${payment.value.id}`);
    if (stopped) return;
    payment.value = result;
    if (result.status === "succeeded" && !notified) {
      notified = true;
      emit("saved", { failed: false, payment: result });
    }
  } catch (e) {
    if (!stopped) error.value = e.message;
  } finally {
    polls++;
    schedule();
  }
}
async function start() {
  busy.value = true;
  error.value = "";
  try {
    const result = await request("POST", `${prefix}/checkouts`, {
      bookingId: props.booking.id,
      requestKey,
      locale: locale.value,
    });
    if (!stopped) {
      payment.value = result;
      schedule();
    }
  } catch (e) {
    if (!stopped) error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function refresh() {
  if (!payment.value || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await request(
      "POST",
      `${prefix}/${payment.value.id}/refresh`,
      {},
    );
    if (!stopped) {
      payment.value = result;
      polls = 0;
      paused.value = false;
      schedule();
    }
  } catch (e) {
    if (!stopped) error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(async () => {
  clock = setInterval(() => {
    now.value = Date.now();
  }, 1000);
  if (props.booking.payment?.provider === "halyk_epay") {
    payment.value = { id: props.booking.payment.id };
    await read();
    if (!terminal.value) await refresh();
  }
});
onBeforeUnmount(() => {
  stopped = true;
  clearTimeout(timer);
  clearInterval(clock);
});
</script>
<template>
  <Modal :title="t('common.payment.title')" :busy="busy" @close="emit('close')">
    <div class="bank-payment">
      <span class="payment-demo-label">{{ t("common.payment.sandbox") }}</span>
      <div class="payment-receipt">
        <span>{{ booking.resortName }}</span>
        <h3>{{ booking.roomName }}</h3>
        <strong>{{ money(payment?.amount ?? booking.total) }}</strong>
      </div>
      <p>{{ t("common.payment.explanation") }}</p>
      <p v-if="!terminal" class="bank-hold">
        {{
          remaining > 0
            ? t("common.payment.hold", { minutes: remaining })
            : t("common.payment.expired")
        }}
      </p>
      <p v-if="payment?.status" role="status" aria-live="polite">
        {{ t(`common.payment.states.${payment.status}`) }}
      </p>
      <p v-if="payment?.refundStatus" role="status">
        {{ t(`common.payment.refunds.${payment.refundStatus}`) }}
      </p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="payment-actions">
        <button
          v-if="!payment"
          class="primary"
          :disabled="busy || !remaining"
          @click="start"
        >
          {{ busy ? t("common.payment.loading") : t("common.payment.create") }}
        </button>
        <a
          v-if="safeUrl"
          class="primary bank-link"
          :href="safeUrl"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          >{{ t("common.payment.open") }}</a
        >
        <button
          v-if="payment && !terminal"
          class="secondary"
          :disabled="busy"
          @click="refresh"
        >
          {{ t("common.payment.refresh") }}
        </button>
      </div>
      <p v-if="paused" class="small muted">{{ t("common.payment.paused") }}</p>
      <p class="small muted">{{ t("common.payment.noReceipt") }}</p>
    </div>
  </Modal>
</template>
<style scoped>
.bank-payment {
  display: grid;
  gap: 1rem;
}
.bank-payment p {
  margin: 0;
}
.bank-hold {
  font-weight: 600;
}
.bank-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
}
.payment-actions {
  display: flex;
  gap: 0.7rem;
  flex-wrap: wrap;
}
.payment-actions > * {
  flex: 1;
  min-height: 44px;
}
</style>
