<script setup>
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { shiftDay } from "@/entities/booking";
import { dateLabel, money } from "@/shared/lib";
const props = defineProps({
  room: { type: Object, required: true },
  start: String,
  end: String,
  expanded: Boolean,
});
const { t } = useI18n();
const periods = computed(() =>
  [...(props.room.pricePeriods || [])].sort((a, b) =>
    a.start.localeCompare(b.start),
  ),
);
const selected = (period) =>
  props.start &&
  props.end &&
  period.start < props.end &&
  props.start < period.end;
</script>
<template>
  <details v-if="periods.length" class="seasonal-prices" :open="expanded">
    <summary>
      {{ t("common.pricing.periods") }} <span>{{ periods.length }}</span>
    </summary>
    <p class="field-help">{{ t("common.pricing.publicPeriodHint") }}</p>
    <ul>
      <li
        v-for="period in periods"
        :key="`${period.start}-${period.end}`"
        :class="{ selected: selected(period) }"
      >
        <div>
          <strong>{{ period.label }}</strong>
          <small
            >{{ dateLabel(period.start) }} —
            {{ dateLabel(shiftDay(period.end, -1)) }}</small
          >
          <span v-if="selected(period)" class="seasonal-selected">{{
            t("common.pricing.inSelectedStay")
          }}</span>
        </div>
        <div class="seasonal-amount">
          <strong>{{ money(period.price) }}</strong
          ><small>{{ t("public.night") }}</small>
        </div>
      </li>
    </ul>
    <p class="field-help">
      {{ t("common.pricing.outsidePeriods", { price: money(room.price) }) }}
    </p>
  </details>
</template>
<style scoped>
.seasonal-prices {
  margin: 1rem 0;
  border: 1px solid #dce3dd;
  border-radius: 14px;
  padding: 0.875rem 1rem;
}
.seasonal-prices summary {
  cursor: pointer;
  font-weight: 700;
  min-height: 1.5rem;
}
.seasonal-prices summary > span {
  margin-left: 0.4rem;
  font-size: 0.85em;
  color: #627168;
}
.seasonal-prices ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.seasonal-prices li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem;
  margin: 0.25rem -0.25rem;
  border-radius: 9px;
}
.seasonal-prices li.selected {
  background: #edf3e8;
}
.seasonal-prices li > div {
  min-width: 0;
}
.seasonal-prices small {
  display: block;
  font-size: 0.8rem;
  color: #627168;
  margin-top: 0.25rem;
}
.seasonal-prices strong {
  overflow-wrap: anywhere;
}
.seasonal-amount {
  text-align: right;
  flex-shrink: 0;
}
.seasonal-selected {
  display: inline-block;
  margin-top: 0.4rem;
  color: #215b49;
  font-size: 0.75rem;
}
.seasonal-prices .field-help:last-child {
  margin-bottom: 0;
}
</style>
