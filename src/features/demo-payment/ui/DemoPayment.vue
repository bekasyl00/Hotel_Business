<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { computed, ref } from "vue";
import { Modal } from "@/shared/ui";
import { PaymentCountdown } from "@/entities/booking";
import { request } from "@/shared/api";
import { money } from "@/shared/lib";
const props = defineProps({
  booking: { type: Object, required: true },
  staff: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const totalAmount = computed(
  () => props.booking.paymentTerms?.total ?? props.booking.total,
);
const onlineAmount = computed(
  () =>
    props.booking.payment?.amount ??
    props.booking.paymentTerms?.onlineAmount ??
    props.booking.total,
);
const onsiteAmount = computed(() =>
  Math.max(0, totalAmount.value - onlineAmount.value),
);
const expired = ref(false);
const busy = ref(false),
  error = ref(""),
  failed = ref(false);
let attempt = null;
async function pay(outcome) {
  if (expired.value) return;
  busy.value = true;
  error.value = "";
  failed.value = false;
  if (attempt?.outcome !== outcome)
    attempt = { outcome, requestId: crypto.randomUUID() };
  try {
    const result = await request(
      "POST",
      props.staff ? "/payments/demo/staff" : "/payments/demo",
      {
        bookingId: props.booking.id,
        outcome,
        requestId: attempt.requestId,
      },
    );
    if (outcome === "failed") {
      failed.value = true;
      attempt = null;
      emit("saved", { failed: true, payment: result });
    } else emit("saved", { failed: false, payment: result });
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <Modal
    :title="t('public.kaspiDemoPayment')"
    :busy="busy"
    @close="emit('close')"
    ><div class="demo-payment">
      <PaymentCountdown :booking="booking" @expired="expired = true" />
      <span class="payment-demo-label">{{
        t("public.demonstrationNoRealCharge")
      }}</span>
      <div class="payment-receipt">
        <span>{{ booking.resortName }}</span>
        <h3>{{ booking.roomName || t("public.room", [booking.unit]) }}</h3>
        <strong>{{ money(totalAmount) }}</strong>
        <span class="small">{{ t("common.settlement.total") }}</span>
      </div>
      <dl v-if="onsiteAmount > 0" class="demo-payment-breakdown">
        <div>
          <dt>{{ t("common.settlement.online") }}</dt>
          <dd>{{ money(onlineAmount) }}</dd>
        </div>
        <div>
          <dt>{{ t("common.settlement.onsite") }}</dt>
          <dd>{{ money(onsiteAmount) }}</dd>
        </div>
      </dl>
      <p>
        {{
          t("public.thisSimulatesAPaymentItDoesNotConnectToKaspiRequestCard")
        }}
      </p>
      <p v-if="failed" class="form-error" role="status">
        {{
          t("public.paymentFailureSimulatedYourBookingIsSavedAndYouCanRetry")
        }}
      </p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="payment-actions">
        <button
          class="primary"
          :disabled="busy || expired"
          @click="pay('success')"
        >
          {{
            busy
              ? t("public.processing")
              : t("public.simulateSuccessfulPayment")
          }}</button
        ><button
          class="secondary"
          :disabled="busy || expired"
          @click="pay('failed')"
        >
          {{ t("public.testPaymentFailure") }}
        </button>
      </div>
      <p class="small muted">
        {{ t("public.theResultWillBeSavedInYourBookingHistory") }}
      </p>
    </div></Modal
  >
</template>
<style scoped>
.demo-payment-breakdown {
  display: grid;
  gap: 0.6rem;
  margin: 0;
}
.demo-payment-breakdown > div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.demo-payment-breakdown dd {
  margin: 0;
  white-space: nowrap;
  font-weight: 600;
}
</style>
