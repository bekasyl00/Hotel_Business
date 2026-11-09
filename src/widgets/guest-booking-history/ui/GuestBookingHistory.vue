<script setup>
import { computed } from "vue";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { money, dateLabel, statusNames } from "@/shared/lib";
import { BookingVoucher, canOpenVoucher } from "@/features/booking-voucher";
import { isDemo } from "@/shared/config";
import { propertyToday } from "@/entities/booking";
defineProps({ bookings: { type: Array, default: () => [] }, staff: Boolean });
const stayNames = computed(() => ({
  not_arrived: t("public.notCheckedIn"),
  in_house: t("public.inHouse"),
  checked_out: t("public.checkedOut"),
}));
function stayLabel(booking) {
  if (booking.stayStatus && booking.stayStatus !== "not_arrived")
    return stayNames.value[booking.stayStatus] || "—";
  if (booking.status === "cancelled") return t("public.stayCancelled");
  if (booking.status === "rejected") return t("public.stayNotConfirmed");
  const today = propertyToday(
    booking.cancellationPolicy?.timeZone || "Asia/Almaty",
  );
  if (booking.end <= today) return t("public.endedNoCheckinRecorded");
  return stayNames.value.not_arrived;
}
</script>
<template>
  <div class="profile-history">
    <div v-if="!bookings.length" class="profile-feedback">
      <h3>{{ t("public.noHistoryYet") }}</h3>
      <p>
        {{
          staff
            ? t("public.thereAreNoAccessibleBookingsForThisGuestAtYourResort")
            : t("public.yourRequestsStaysAndDemoPaymentsWillAppearHere")
        }}
      </p>
      <RouterLink v-if="!staff" class="secondary button-link" to="/">{{
        t("public.chooseAResortInGuestBookingHistory")
      }}</RouterLink>
    </div>
    <article
      v-for="booking in bookings"
      :key="booking.id"
      class="guest-booking"
    >
      <div class="guest-booking-heading">
        <div>
          <span :class="['status-pill', booking.status]">{{
            statusNames[booking.status]
          }}</span>
          <h2>{{ booking.resortName }}</h2>
          <p>{{ booking.roomName }} · № {{ booking.unit }}</p>
        </div>
        <strong>{{
          money(booking.paymentTerms?.total ?? booking.total)
        }}</strong>
      </div>
      <dl class="guest-booking-facts">
        <div v-if="booking.paymentTerms?.version === 1">
          <dt>
            {{
              t(
                booking.status === "pending"
                  ? "common.settlement.online"
                  : "common.voucher.online",
              )
            }}
          </dt>
          <dd>{{ money(booking.paymentTerms.onlineAmount) }}</dd>
        </div>
        <div v-if="booking.paymentTerms?.version === 1">
          <dt>{{ t("common.settlement.onsite") }}</dt>
          <dd>{{ money(booking.paymentTerms.onsiteAmount) }}</dd>
        </div>
        <div>
          <dt>{{ t("public.stayDates") }}</dt>
          <dd>{{ dateLabel(booking.start) }} — {{ dateLabel(booking.end) }}</dd>
        </div>
        <div>
          <dt>{{ t("public.guestsAndRate") }}</dt>
          <dd>{{ booking.guests }} · {{ booking.tariffName }}</dd>
        </div>
        <div>
          <dt>{{ t("public.stay") }}</dt>
          <dd>{{ stayLabel(booking) }}</dd>
        </div>
        <div>
          <dt>{{ t("public.bookingReference") }}</dt>
          <dd class="booking-reference">{{ booking.id }}</dd>
        </div>
      </dl>
      <div class="guest-booking-actions">
        <BookingVoucher
          v-if="!isDemo && canOpenVoucher(booking)"
          :booking="booking"
        />
        <RouterLink
          v-if="booking.payment?.receiptUrl"
          class="secondary button-link"
          :to="booking.payment.receiptUrl"
          >{{ t("public.demoReceipt") }}</RouterLink
        ><RouterLink
          v-if="!staff && ['pending', 'confirmed'].includes(booking.status)"
          class="text-button"
          to="/bookings"
          >{{ t("public.manageBooking") }}</RouterLink
        ><span v-if="booking.payment?.refundedAmount" class="small muted"
          >{{ t("public.refunded") }}
          {{ money(booking.payment.refundedAmount) }}</span
        >
        <span
          v-if="booking.payment?.refundStatus"
          class="small muted"
          role="status"
        >
          {{ t(`common.payment.refunds.${booking.payment.refundStatus}`) }}
        </span>
      </div>
    </article>
  </div>
</template>
