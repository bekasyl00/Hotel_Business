<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "@/shared/ui";
import { PaymentCountdown } from "@/entities/booking";
import { request } from "@/shared/api";
import { money } from "@/shared/lib";
import { isBankProvider, safeCheckoutUrl } from "../model/provider.js";
import { createPaymentQrRenderer } from "../model/qr.js";
const props = defineProps({
  booking: { type: Object, required: true },
  staff: Boolean,
  provider: { type: String, default: "" },
  environment: { type: String, default: "" },
  available: Boolean,
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
const provider = computed(
  () =>
    payment.value?.provider ||
    (isBankProvider(props.booking.payment?.provider)
      ? props.booking.payment.provider
      : props.provider),
);
const environment = computed(
  () =>
    payment.value?.environment ||
    (isBankProvider(props.booking.payment?.provider)
      ? props.booking.payment.paymentMode
      : props.environment),
);
let stopped = false,
  timer,
  clock,
  polls = 0,
  notified = props.booking.payment?.checkoutStatus === "succeeded";
const expires = computed(() => {
  const deadlines = [
    payment.value?.expiresAt,
    props.booking.status === "pending" ? props.booking.holdExpiresAt : null,
  ]
    .map((v) => Date.parse(v || ""))
    .filter(Number.isFinite);
  return deadlines.length ? Math.min(...deadlines) : NaN;
});
const remaining = computed(() =>
  Number.isFinite(expires.value)
    ? Math.max(0, Math.ceil((expires.value - now.value) / 60000))
    : 0,
);
const terminal = computed(() =>
  ["succeeded", "expired", "reconciliation_required"].includes(
    payment.value?.status,
  ),
);
const safeUrl = computed(() => {
  if (terminal.value || !payment.value?.checkoutUrl || remaining.value <= 0)
    return null;
  return safeCheckoutUrl(
    provider.value,
    payment.value.checkoutUrl,
    environment.value,
  );
});
const qr = ref({ status: "idle", src: "" });
const qrRenderer = createPaymentQrRenderer((value) => {
  qr.value = value;
});
watch(
  [safeUrl, provider, environment, expires],
  ([url, paymentProvider, paymentEnvironment, expiresAt]) => {
    void qrRenderer.update({
      provider: paymentProvider,
      environment: paymentEnvironment,
      url,
      expiresAt,
    });
  },
  { immediate: true },
);
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
  if (!props.available || !isBankProvider(provider.value) || !remaining.value)
    return;
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
  if (isBankProvider(props.booking.payment?.provider)) {
    payment.value = { id: props.booking.payment.id };
    await read();
    if (!terminal.value) await refresh();
  }
});
onBeforeUnmount(() => {
  stopped = true;
  qrRenderer.dispose();
  clearTimeout(timer);
  clearInterval(clock);
});
</script>
<template>
  <Modal :title="t('common.payment.title')" :busy="busy" @close="emit('close')">
    <div class="bank-payment">
      <PaymentCountdown :booking="booking" />
      <span class="payment-demo-label">{{
        provider === "xpayment"
          ? t("common.payment.kaspiXPayment")
          : t("common.payment.halykSandbox")
      }}</span>
      <p v-if="environment === 'sandbox'" class="small muted">
        {{ t("common.payment.sandbox") }}
      </p>
      <p v-else-if="environment === 'production'" class="small muted">
        {{ t("common.payment.production") }}
      </p>
      <div class="payment-receipt">
        <span>{{ booking.resortName }}</span>
        <h3>{{ booking.roomName }}</h3>
        <strong>{{ money(payment?.amount ?? booking.total) }}</strong>
      </div>
      <p>
        {{
          t(
            environment === "sandbox" && provider === "xpayment"
              ? "common.payment.xpaymentSandboxExplanation"
              : provider === "xpayment"
                ? "common.payment.kaspiExplanation"
                : "common.payment.explanation",
          )
        }}
      </p>
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
          :disabled="busy || !remaining || !available"
          @click="start"
        >
          {{
            busy
              ? t("common.payment.loading")
              : t(
                  provider === "xpayment"
                    ? "common.payment.createKaspi"
                    : "common.payment.create",
                )
          }}
        </button>
        <a
          v-if="safeUrl"
          class="primary bank-link"
          :href="safeUrl"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          >{{
            t(
              environment === "sandbox" && provider === "xpayment"
                ? "common.payment.openXPaymentSandbox"
                : provider === "xpayment"
                  ? "common.payment.openKaspi"
                  : "common.payment.open",
            )
          }}</a
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
      <div
        v-if="
          safeUrl && provider === 'xpayment' && environment === 'production'
        "
        class="payment-qr"
      >
        <strong>{{ t("common.payment.qrTitle") }}</strong>
        <p class="small">{{ t("common.payment.qrInstructions") }}</p>
        <img
          v-if="qr.status === 'ready'"
          :src="qr.src"
          :alt="t('common.payment.qrAlt')"
          width="256"
          height="256"
        />
        <p
          v-else-if="qr.status === 'loading'"
          class="small muted"
          role="status"
        >
          {{ t("common.payment.qrLoading") }}
        </p>
        <p v-else-if="qr.status === 'error'" class="form-error" role="alert">
          {{ t("common.payment.qrUnavailable") }}
        </p>
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
.payment-qr {
  display: grid;
  justify-items: center;
  gap: 0.6rem;
  padding: 1rem;
  border: 1px solid var(--line, #dce4df);
  border-radius: 16px;
  text-align: center;
}
.payment-qr img {
  display: block;
  max-width: 100%;
  height: auto;
  background: #fff;
}
</style>
