<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "@/shared/ui";
import { PaymentCountdown } from "@/entities/booking";
import { request } from "@/shared/api";
import { money } from "@/shared/lib";
import { isBankProvider, safeCheckoutUrl } from "../model/provider.js";
import { createPaymentQrRenderer } from "../model/qr.js";
import {
  checkoutAmounts,
  paymentNeedsPolling,
  paymentStage,
} from "../model/presentation.js";
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
  paused = ref(false),
  opened = ref(false);
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
  reading = false,
  timer,
  clock,
  polls = 0,
  notified = props.booking.payment?.checkoutStatus === "succeeded",
  refundNotified = props.booking.payment?.refundStatus === "succeeded";
const amounts = computed(() => checkoutAmounts(props.booking, payment.value));
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
const stage = computed(() =>
  paymentStage(payment.value, {
    hasLink: !!safeUrl.value,
    opened: opened.value,
  }),
);
const waiting = computed(() =>
  [
    "loading",
    "creating",
    "verifying",
    "refund_queued",
    "refund_submitted",
  ].includes(stage.value),
);
const stageIndex = computed(
  () =>
    ({
      initial: 0,
      loading: 0,
      creating: 0,
      ready: 1,
      verifying: 2,
      succeeded: 3,
    })[stage.value],
);
const statusText = computed(() => {
  if (payment.value?.refundStatus)
    return t(`common.payment.refunds.${payment.value.refundStatus}`);
  if (["expired", "failed", "reconciliation_required"].includes(stage.value))
    return t(`common.payment.states.${stage.value}`);
  return t(`common.payment.progress.${stage.value}`);
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
  if (
    stopped ||
    !paymentNeedsPolling(payment.value) ||
    document.hidden ||
    polls >= 90
  ) {
    paused.value = polls >= 90 && paymentNeedsPolling(payment.value);
    return;
  }
  timer = setTimeout(
    read,
    payment.value?.status === "creating"
      ? 2000
      : Math.min(3000 + polls * 250, 8000),
  );
}
function accept(result) {
  payment.value = result;
  error.value = "";
  if (result.refundStatus === "succeeded" && !refundNotified) {
    refundNotified = true;
    emit("saved", { failed: false, payment: result });
  } else if (
    result.status === "succeeded" &&
    !result.refundStatus &&
    !notified
  ) {
    notified = true;
    emit("saved", { failed: false, payment: result });
  }
}
async function read() {
  if (stopped || !payment.value || reading || busy.value) return;
  reading = true;
  try {
    const result = await request("GET", `${prefix}/${payment.value.id}`);
    if (!stopped) accept(result);
  } catch (e) {
    if (!stopped) error.value = e.message;
  } finally {
    reading = false;
    polls++;
    schedule();
  }
}
async function start() {
  if (
    busy.value ||
    !props.available ||
    !isBankProvider(provider.value) ||
    !remaining.value
  )
    return;
  busy.value = true;
  error.value = "";
  try {
    const result = await request("POST", `${prefix}/checkouts`, {
      bookingId: props.booking.id,
      requestKey,
      locale: locale.value,
    });
    if (!stopped) accept(result);
  } catch (e) {
    if (!stopped) error.value = e.message;
  } finally {
    busy.value = false;
    schedule();
  }
}
async function refresh() {
  if (!payment.value || busy.value || reading || stopped) return;
  clearTimeout(timer);
  busy.value = true;
  error.value = "";
  try {
    const result = await request(
      "POST",
      `${prefix}/${payment.value.id}/refresh`,
      {},
    );
    if (!stopped) {
      accept(result);
      polls = 0;
      paused.value = false;
    }
  } catch (e) {
    if (!stopped) error.value = e.message;
  } finally {
    busy.value = false;
    schedule();
  }
}
function resume() {
  if (document.hidden || stopped) return;
  polls = 0;
  paused.value = false;
  if (paymentNeedsPolling(payment.value)) void refresh();
}
function visibilityChanged() {
  if (document.hidden) clearTimeout(timer);
  else resume();
}
onMounted(async () => {
  clock = setInterval(() => {
    now.value = Date.now();
  }, 1000);
  window.addEventListener("focus", resume);
  document.addEventListener("visibilitychange", visibilityChanged);
  if (isBankProvider(props.booking.payment?.provider)) {
    payment.value = {
      ...props.booking.payment,
      status: props.booking.payment.checkoutStatus,
      environment: props.booking.payment.paymentMode,
    };
    await read();
    if (paymentNeedsPolling(payment.value)) await refresh();
  }
});
onBeforeUnmount(() => {
  stopped = true;
  qrRenderer.dispose();
  clearTimeout(timer);
  clearInterval(clock);
  window.removeEventListener("focus", resume);
  document.removeEventListener("visibilitychange", visibilityChanged);
});
</script>
<template>
  <Modal :title="t('common.payment.title')" :busy="busy" @close="emit('close')">
    <div class="bank-payment">
      <div class="payment-provider">
        <span>{{
          provider === "xpayment"
            ? t("common.payment.kaspiXPayment")
            : t("common.payment.halykSandbox")
        }}</span>
        <span v-if="environment === 'sandbox'" class="small muted">{{
          t("common.payment.sandbox")
        }}</span>
      </div>
      <div class="payment-summary">
        <span class="small muted"
          >{{ booking.resortName }} · {{ booking.roomName }}</span
        >
        <strong class="payment-amount">{{ money(amounts.online) }}</strong>
        <span class="small">{{
          t(
            booking.paymentTerms?.version === 1
              ? "common.payment.onlineCommission"
              : "common.payment.onlineAmount",
          )
        }}</span>
        <dl v-if="amounts.onsite > 0" class="payment-breakdown">
          <div>
            <dt>{{ t("common.payment.totalAmount") }}</dt>
            <dd>{{ money(amounts.total) }}</dd>
          </div>
          <div>
            <dt>{{ t("common.payment.onsiteAmount") }}</dt>
            <dd>{{ money(amounts.onsite) }}</dd>
          </div>
        </dl>
      </div>
      <PaymentCountdown :booking="booking" compact />
      <ol
        v-if="stageIndex !== undefined"
        class="payment-steps"
        :aria-label="t('common.payment.progressLabel')"
      >
        <li
          v-for="(step, index) in [
            'invoice',
            'bank',
            'verification',
            'confirmed',
          ]"
          :key="step"
          :class="{
            current: index === stageIndex,
            complete: index < stageIndex,
          }"
          :aria-current="index === stageIndex ? 'step' : undefined"
        >
          <span class="step-dot" aria-hidden="true">{{
            index < stageIndex ? "✓" : index + 1
          }}</span>
          <span>{{ t(`common.payment.steps.${step}`) }}</span>
        </li>
      </ol>
      <div
        class="payment-status"
        :class="{
          waiting,
          success: stage === 'succeeded' || stage === 'refund_succeeded',
        }"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <span
          v-if="waiting || busy"
          class="payment-spinner"
          aria-hidden="true"
        ></span>
        <div>
          <strong>{{
            busy && !payment
              ? t("common.payment.progress.creating")
              : statusText
          }}</strong>
          <p v-if="waiting" class="small muted">
            {{ t("common.payment.waitingHint") }}
          </p>
          <p v-else-if="stage === 'ready'" class="small muted">
            {{ t("common.payment.readyHint") }}
          </p>
          <p v-if="payment?.refundStatus === 'succeeded'" class="small">
            {{ money(payment.refundedAmount) }}
          </p>
        </div>
      </div>
      <p v-if="error" class="form-error small" role="alert">{{ error }}</p>
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
          @click="opened = true"
        >
          {{
            t(
              environment === "sandbox" && provider === "xpayment"
                ? "common.payment.openXPaymentSandbox"
                : provider === "xpayment"
                  ? "common.payment.openKaspi"
                  : "common.payment.open",
            )
          }}
        </a>
        <button
          v-if="payment && (paymentNeedsPolling(payment) || error)"
          class="secondary"
          :disabled="busy"
          @click="refresh"
        >
          {{
            busy
              ? t("common.payment.loading")
              : t(
                  payment.refundStatus
                    ? "common.payment.refreshRefund"
                    : "common.payment.refresh",
                )
          }}
        </button>
      </div>
      <details
        v-if="
          safeUrl && provider === 'xpayment' && environment === 'production'
        "
        class="payment-help payment-qr"
      >
        <summary>{{ t("common.payment.qrTitle") }}</summary>
        <div class="payment-qr-content">
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
      </details>
      <details class="payment-help">
        <summary>{{ t("common.payment.howItWorks") }}</summary>
        <p class="small muted">{{ t("common.checkout.holdHint") }}</p>
        <p class="small muted">
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
        <p class="small muted">{{ t("common.payment.noReceipt") }}</p>
      </details>
      <p v-if="paused" class="small muted">{{ t("common.payment.paused") }}</p>
      <p v-if="!terminal && remaining <= 0" class="small muted">
        {{ t("common.payment.expired") }}
      </p>
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
.payment-provider {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  justify-content: space-between;
  font-size: 0.8rem;
  font-weight: 600;
}
.payment-summary {
  display: grid;
  gap: 0.3rem;
  text-align: center;
  padding: 0.4rem 0;
}
.payment-amount {
  font-size: clamp(1.75rem, 6vw, 2.5rem);
  line-height: 1.2;
  letter-spacing: -0.04em;
}
.payment-breakdown {
  display: grid;
  gap: 0.5rem;
  margin: 0.7rem 0 0;
  padding-top: 0.8rem;
  border-top: 1px solid var(--line, #dce4df);
  font-size: 0.85rem;
}
.payment-breakdown > div {
  display: flex;
  justify-content: space-between;
  gap: 0.7rem;
  text-align: left;
}
.payment-breakdown dd {
  margin: 0;
  white-space: nowrap;
  font-weight: 600;
}
.payment-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  list-style: none;
  padding: 0;
  margin: 0;
  gap: 0.4rem;
}
.payment-steps li {
  display: grid;
  justify-items: center;
  text-align: center;
  gap: 0.4rem;
  font-size: 0.68rem;
  color: var(--muted, #64736c);
  overflow-wrap: anywhere;
}
.step-dot {
  display: grid;
  place-items: center;
  width: 1.7rem;
  height: 1.7rem;
  border: 1px solid var(--line, #dce4df);
  border-radius: 50%;
  font-weight: 700;
  background: #f6f7f3;
}
.current .step-dot,
.complete .step-dot {
  background: #245e4e;
  border-color: #245e4e;
  color: #fff;
}
.payment-steps .current {
  color: #245e4e;
  font-weight: 700;
}
.payment-status {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  border-radius: 14px;
  padding: 0.9rem;
  background: #f4f6f1;
  font-size: 0.9rem;
}
.payment-status .small {
  margin-top: 0.3rem;
  font-size: 0.8rem;
  line-height: 1.45;
}
.payment-status.success {
  background: #eaf5ed;
}
.payment-spinner {
  flex: 0 0 auto;
  width: 1.4rem;
  height: 1.4rem;
  border: 2px solid #c7dacf;
  border-top-color: #245e4e;
  border-radius: 50%;
  animation: payment-spin 1s linear infinite;
}
@keyframes payment-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .payment-spinner {
    animation: none;
    border-style: dotted;
  }
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
  font-size: 0.9rem;
}
.payment-help {
  border-top: 1px solid var(--line, #dce4df);
  font-size: 0.85rem;
}
.payment-help summary {
  cursor: pointer;
  padding: 0.7rem 0;
  min-height: 44px;
  font-weight: 600;
}
.payment-help summary:focus-visible {
  outline: 2px solid #245e4e;
  outline-offset: 3px;
  border-radius: 4px;
}
.payment-help > p {
  padding: 0 0 0.7rem;
  font-size: 0.8rem;
  line-height: 1.5;
}
.payment-qr-content {
  display: grid;
  justify-items: center;
  gap: 0.6rem;
  padding: 0 0 0.6rem;
  text-align: center;
}
.payment-qr img {
  display: block;
  max-width: 100%;
  height: auto;
  background: #fff;
}
</style>
