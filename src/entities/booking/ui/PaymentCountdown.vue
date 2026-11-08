<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { holdSeconds, holdLabel } from "../model/hold.js";
const props = defineProps({ booking: { type: Object, required: true } });
const emit = defineEmits(["expired"]);
const { t } = useI18n();
const now = ref(Date.now());
const active = computed(
  () =>
    props.booking.status === "pending" && Boolean(props.booking.holdExpiresAt),
);
const seconds = computed(() =>
  holdSeconds(props.booking.holdExpiresAt, now.value),
);
let timer,
  notified = "";
watch([active, seconds], () => {
  const key = props.booking.id + ":" + props.booking.holdExpiresAt;
  if (active.value && seconds.value === 0 && key !== notified) {
    notified = key;
    emit("expired");
  }
});
onMounted(() => {
  now.value = Date.now();
  timer = setInterval(() => (now.value = Date.now()), 1000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <div
    v-if="active"
    class="payment-countdown"
    :class="{ ended: seconds === 0 }"
  >
    <template v-if="seconds > 0"
      ><span>{{ t("common.checkout.timeLeft") }}</span
      ><strong role="timer" aria-live="off">{{ holdLabel(seconds) }}</strong
      ><small>{{ t("common.checkout.holdHint") }}</small></template
    >
    <p v-else role="status">{{ t("common.checkout.timeExpired") }}</p>
  </div>
</template>
<style scoped>
.payment-countdown {
  display: flex;
  align-items: center;
  gap: 10px 18px;
  flex-wrap: wrap;
  padding: 16px;
  background: #eef5e8;
  border: 1px solid #cadbbd;
  border-radius: 14px;
  margin: 16px 0;
}
.payment-countdown strong {
  font-size: 26px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
}
.payment-countdown small {
  flex-basis: 100%;
  color: #46554a;
}
.payment-countdown.ended {
  background: #fff4df;
  border-color: #d5b879;
}
.payment-countdown p {
  margin: 0;
}
</style>
