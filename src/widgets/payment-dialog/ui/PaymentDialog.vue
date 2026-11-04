<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { PayBooking } from "@/features/pay-booking";
import { DemoPayment } from "@/features/demo-payment";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
const props = defineProps({
  booking: { type: Object, required: true },
  staff: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const { t } = useI18n();
const config = ref(null),
  error = ref("");
onMounted(async () => {
  try {
    config.value = isDemo
      ? { provider: "simulator", available: true }
      : await request("GET", "/payments/config");
  } catch (e) {
    error.value = e.message;
  }
});
</script>
<template>
  <DemoPayment
    v-if="
      config?.available &&
      config.provider === 'simulator' &&
      booking.payment?.provider !== 'halyk_epay'
    "
    v-bind="props"
    @close="emit('close')"
    @saved="emit('saved', $event)"
  />
  <PayBooking
    v-else-if="
      (config?.available && config.provider === 'halyk_epay') ||
      booking.payment?.provider === 'halyk_epay'
    "
    v-bind="props"
    @close="emit('close')"
    @saved="emit('saved', $event)"
  />
  <Modal v-else :title="t('common.payment.title')" @close="emit('close')">
    <p role="status">
      {{
        error ||
        (config ? t("common.payment.unavailable") : t("common.payment.loading"))
      }}
    </p>
  </Modal>
</template>
