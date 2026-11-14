<script setup>
import { useI18n } from "vue-i18n";
import { timeLabel, statusNames } from "@/shared/lib";
import { computed } from "vue";
const { t } = useI18n();
defineProps(["filteredAudit"]);
function changes(entry) {
  const keys = new Set([
    ...Object.keys(entry.before || {}),
    ...Object.keys(entry.after || {}),
  ]);
  return [...keys]
    .filter(
      (k) =>
        !["id", "version", "rating", "ownerId"].includes(k) &&
        JSON.stringify(entry.before?.[k]) !== JSON.stringify(entry.after?.[k]),
    )
    .map((key) => ({
      key,
      before: entry.before?.[key],
      after: entry.after?.[key],
    }));
}
const fieldNames = computed(() => ({
  notesLength: t("staff.board.notesLength"),
  checkInTime: t("staff.checkInTime"),
  timeZone: t("staff.timeZone"),
  resortClass: t("staff.class"),
  priceKind: t("staff.priceKind"),
  discountPercent: t("staff.discount"),
  payment: t("staff.payment"),
  cancellationPolicy: t("staff.refundTerms"),
  cancellation: t("staff.cancellationResult"),
  guestProfileId: t("staff.guestProfile"),
  checkedInAt: t("staff.actualArrival"),
  checkedOutAt: t("staff.actualDeparture"),
  stayStatus: t("staff.stayStatus"),
  name: t("staff.name"),
  status: t("staff.status"),
  price: t("staff.price"),
  supplement: t("staff.supplement"),
  number: t("staff.room"),
  capacity: t("staff.capacity"),
  area: t("staff.area"),
  lat: t("staff.latitude"),
  lng: t("staff.longitude"),
  address: t("staff.address"),
  city: t("staff.city"),
  description: t("staff.description"),
  subtitle: t("staff.shortDescription"),
  feature: t("staff.service"),
  features: t("staff.services"),
  beds: t("staff.beds"),
  category: t("staff.category"),
  title: t("staff.name"),
  login: t("staff.login"),
  resortId: t("staff.resort"),
  start: t("staff.arrival"),
  end: t("staff.departure"),
  guests: t("staff.guests"),
  total: t("staff.amount"),
  guestLabel: t("staff.guest"),
  roomId: t("staff.physicalRoom"),
  tariffId: t("staff.tariff"),
}));
const display = (value) =>
  value == null
    ? "—"
    : Array.isArray(value)
      ? value.join(", ")
      : typeof value === "object"
        ? JSON.stringify(value)
        : statusNames[value] ||
          {
            regular: t("staff.regularPrice"),
            discount: t("staff.discountPrice"),
            not_arrived: t("staff.awaitingArrival"),
            in_house: t("staff.inHousePaid"),
            checked_out: t("staff.checkedOut"),
            website: t("staff.website"),
            staff: t("staff.manual"),
          }[value] ||
          String(value);
</script>
<template>
  <div class="audit-list">
    <details v-for="entry in filteredAudit" :key="entry.id">
      <summary>
        <span :class="['audit-dot', entry.action]">{{
          {
            create: "+",
            update: "↗",
            delete: "−",
            archive: "□",
            cancel: "×",
            cancelled: "×",
            demo_payment: "₸",
            demo_refund: "↩",
            "check-in": "↳",
            "check-out": "↰",
            payment: "₸",
            refund: "↶",
            confirmed: "✓",
            rejected: "×",
          }[entry.action]
        }}</span
        ><span
          ><strong
            >{{
              {
                notes: t("staff.board.notesSaved"),
                create: t("staff.created"),
                update: t("staff.updated"),
                delete: t("staff.deleted"),
                archive: t("staff.archiving"),
                cancel: t("staff.cancel"),
                cancelled: t("staff.cancel"),
                demo_payment: t("staff.demoPayment"),
                payment_confirmed: t("common.checkout.paymentBooked"),
                payment_expired: t("common.status.expired"),
                demo_refund: t("staff.demoRefund"),
                "check-in": t("staff.checkedIn"),
                "check-out": t("staff.departure"),
                payment: t("staff.demoPayment"),
                refund: t("staff.demoRefund"),
                confirmed: t("staff.approval"),
                rejected: t("staff.rejection"),
              }[entry.action]
            }}
            · {{ entry.label }}</strong
          ><small
            >{{ entry.actor }} · {{ timeLabel(entry.at) }}
            {{ t("staff.almatySuffix") }}</small
          ></span
        ><span class="audit-expand">{{ t("staff.details") }}</span>
      </summary>
      <div class="audit-detail">
        <table class="workspace-table">
          <thead>
            <tr>
              <th>{{ t("staff.field") }}</th>
              <th>{{ t("staff.before") }}</th>
              <th>{{ t("staff.after") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="change in changes(entry)" :key="change.key">
              <td :data-label="t('staff.field')">
                {{ fieldNames[change.key] || change.key }}
              </td>
              <td :data-label="t('staff.before')">
                {{ display(change.before) }}
              </td>
              <td :data-label="t('staff.after')">
                {{ display(change.after) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!changes(entry).length" class="field-help">
          {{ t("staff.noFieldChanges") }}
        </p>
      </div>
    </details>
  </div>
</template>
