<script setup>
import { useI18n } from "vue-i18n";
import { money, dateLabel } from "@/shared/lib";
defineProps({ price: Object, prominent: Boolean });
const { t } = useI18n();
</script>
<template>
  <div
    v-if="price"
    class="customer-night-price"
    :class="[{ prominent }, `price-${price.kind}`]"
  >
    <div class="customer-price-line">
      <del
        v-if="price.kind === 'discount'"
        :aria-label="
          t('common.pricing.beforePrice', { price: money(price.regularPrice) })
        "
        >{{ money(price.regularPrice) }}</del
      >
      <strong>{{ money(price.price) }}</strong>
      <span class="customer-price-unit">{{ t("public.night") }}</span>
      <span v-if="price.kind === 'seasonal'" class="customer-season-badge">{{
        t("common.pricing.seasonalPrice")
      }}</span>
    </div>
    <span class="customer-price-date">{{
      t("common.pricing.nightOnDate", { date: dateLabel(price.date) })
    }}</span>
  </div>
</template>
<style scoped>
.customer-night-price {
  min-width: 0;
}
.customer-price-line {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.35rem 0.5rem;
}
.customer-price-line strong {
  font-size: 1.2rem;
}
.price-discount .customer-price-line strong {
  color: #176247;
}
.price-seasonal .customer-price-line strong {
  color: #805018;
  background: #fff5e7;
  border-radius: 5px;
  padding: 0.1rem 0.3rem;
}
.prominent .customer-price-line strong {
  font-size: 1.8rem;
}
.customer-price-line del {
  font-size: 0.8rem;
  color: #6d746d;
}
.customer-price-unit,
.customer-price-date {
  font-size: 0.72rem;
  color: #667269;
}
.customer-price-date {
  display: block;
  margin-top: 0.2rem;
}
.customer-season-badge {
  background: #fff1da;
  color: #795121;
  border-radius: 5px;
  padding: 0.2rem 0.4rem;
  font-size: 0.65rem;
  line-height: 1.4;
}
</style>
