<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { ref } from "vue";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { money } from "@/shared/lib";
const props = defineProps({
  booking: { type: Object, required: true },
  staff: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const busy = ref(false),
  error = ref(""),
  failed = ref(false);
let attempt = null;
async function pay(outcome) {
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
      <span class="payment-demo-label">{{
        t("public.demonstrationNoRealCharge")
      }}</span>
      <div class="payment-receipt">
        <span>{{ booking.resortName }}</span>
        <h3>{{ booking.roomName || t("public.room", [booking.unit]) }}</h3>
        <strong>{{ money(booking.total) }}</strong>
      </div>
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
        <button class="primary" :disabled="busy" @click="pay('success')">
          {{
            busy
              ? t("public.processing")
              : t("public.simulateSuccessfulPayment")
          }}</button
        ><button class="secondary" :disabled="busy" @click="pay('failed')">
          {{ t("public.testPaymentFailure") }}
        </button>
      </div>
      <p class="small muted">
        {{ t("public.theResultWillBeSavedInYourBookingHistory") }}
      </p>
    </div></Modal
  >
</template>
