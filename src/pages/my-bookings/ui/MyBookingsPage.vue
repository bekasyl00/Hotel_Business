<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { onMounted, ref, computed } from "vue";
import { PublicHeader } from "@/widgets/public-header";
import { DemoPayment } from "@/features/demo-payment";
import { ReviewForm } from "@/features/review-form";
import { useBookingStore, dateAfter } from "@/entities/booking";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { money, dateLabel, statusNames } from "@/shared/lib";
const store = useBookingStore();
const loading = ref(true),
  error = ref(""),
  notice = ref(""),
  paymentTarget = ref(null),
  reviewTarget = ref(null),
  cancelTarget = ref(null),
  preview = ref(null),
  previewLoading = ref(false),
  cancelError = ref(""),
  busy = ref(false),
  reviewed = ref(new Set());
const paymentNames = computed(() => ({
  paid: t("public.paidDemo"),
  failed: t("public.paymentFailedDemo"),
  partially_refunded: t("public.partiallyRefundedDemo"),
  refunded: t("public.refundedDemo"),
}));
const canCancel = (booking) =>
  ["pending", "confirmed"].includes(booking.status) &&
  booking.end > dateAfter() &&
  !booking.checkedInAt;
const canReview = (booking) =>
  booking.status === "confirmed" &&
  booking.end <= dateAfter() &&
  !booking.reviewId &&
  !reviewed.value.has(booking.id);
const canPay = (booking) =>
  booking.status === "confirmed" &&
  Date.parse(booking.cancellationPolicy?.checkinAt || "") > Date.now() &&
  (!booking.payment || booking.payment.status === "failed");
function checkinLabel(booking) {
  const at = booking.cancellationPolicy?.checkinAt;
  if (!at)
    return t("public.checkinTimeToBeConfirmed", [dateLabel(booking.start)]);
  const match = at.match(/T(\d{2}:\d{2})/);
  return t("public.fromInMyBookingsPage", [
    dateLabel(booking.start),
    match?.[1] || "—",
    booking.cancellationPolicy.timeZone || `UTC${at.slice(-6)}`,
  ]);
}
async function load() {
  loading.value = true;
  error.value = "";
  try {
    await store.loadMine();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
async function openCancel(booking) {
  cancelTarget.value = booking;
  preview.value = null;
  cancelError.value = "";
  previewLoading.value = true;
  try {
    preview.value = await request("GET", `/cancellation-preview/${booking.id}`);
  } catch (e) {
    cancelError.value = e.message;
  } finally {
    previewLoading.value = false;
  }
}
async function cancel() {
  busy.value = true;
  cancelError.value = "";
  try {
    await store.cancel(cancelTarget.value);
    cancelTarget.value = null;
    notice.value = t(
      "public.bookingCancelledTheDemoRefundResultIsSavedInYourHistory",
    );
    await load();
  } catch (e) {
    cancelError.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function paymentSaved(result) {
  if (!result.failed) {
    paymentTarget.value = null;
    notice.value = t("public.demoPaymentSuccessfulNoRealMoneyWasCharged");
  }
  await load();
}
async function reviewSaved() {
  reviewed.value.add(reviewTarget.value.id);
  reviewTarget.value = null;
  notice.value = t(
    "public.thankYouYourReviewWasSentForModerationAndWillAppearAfter",
  );
  await load();
}
onMounted(load);
</script>
<template>
  <div class="public-site">
    <PublicHeader />
    <main id="public-main" class="profile-main bookings-main">
      <RouterLink class="profile-back" to="/">{{
        t("public.chooseAResort")
      }}</RouterLink>
      <header class="profile-heading">
        <div>
          <span class="eyebrow">{{ t("public.yourBreak") }}</span>
          <h1>{{ t("public.myBookings") }}</h1>
          <p>{{ t("public.requestStatusPaymentAndMemoriesOfYourStay") }}</p>
        </div>
        <button class="secondary" :disabled="loading" @click="load">
          {{ t("public.refresh") }}
        </button>
      </header>
      <p class="public-session-note">
        {{
          t(
            "public.bookingsCreatedInThisBrowserAppearHereKeepYourBookingReferenceClearing",
          )
        }}
      </p>
      <p v-if="notice" class="success-notice" role="status">{{ notice }}</p>
      <div v-if="error" class="profile-feedback" role="alert">
        <p>{{ error }}</p>
        <button class="secondary" @click="load">{{ t("public.retry") }}</button>
      </div>
      <div v-else-if="loading" class="profile-feedback" role="status">
        {{ t("public.loadingBookings") }}
      </div>
      <div v-else-if="!store.items.length" class="profile-feedback">
        <h2>{{ t("public.yourFirstTripIsAhead") }}</h2>
        <p>{{ t("public.chooseAResortAndRequestTheRoomYouLike") }}</p>
        <RouterLink class="primary button-link" to="/">{{
          t("public.findAResortInMyBookingsPage")
        }}</RouterLink>
      </div>
      <article
        v-for="booking in store.items"
        :key="booking.id"
        class="guest-booking"
      >
        <div class="guest-booking-heading">
          <div>
            <span :class="['status-pill', booking.status]">{{
              statusNames[booking.status]
            }}</span
            ><RouterLink :to="`/resorts/${booking.resortId}`"
              ><h2>{{ booking.resortName }}</h2></RouterLink
            ><RouterLink :to="`/rooms/${booking.roomId}`">{{
              booking.roomName || t("public.room", [booking.unit])
            }}</RouterLink>
          </div>
          <strong class="guest-booking-total">{{
            money(booking.total)
          }}</strong>
        </div>
        <dl class="guest-booking-facts">
          <div>
            <dt>{{ t("public.checkin") }}</dt>
            <dd>{{ checkinLabel(booking) }}</dd>
          </div>
          <div>
            <dt>{{ t("public.checkout") }}</dt>
            <dd>{{ dateLabel(booking.end) }}</dd>
          </div>
          <div>
            <dt>{{ t("public.guestsAndRate") }}</dt>
            <dd>{{ booking.guests }} · {{ booking.tariffName }}</dd>
          </div>
          <div>
            <dt>{{ t("public.bookingReference") }}</dt>
            <dd class="booking-reference">{{ booking.id }}</dd>
          </div>
        </dl>
        <p v-if="booking.status === 'pending'" class="booking-status-note">
          {{
            t(
              "public.waitingForManagerConfirmationYourRoomIsHeldWhileTheRequestIs",
            )
          }}
        </p>
        <p
          v-if="booking.status === 'confirmed' && !booking.payment"
          class="booking-status-note"
        >
          {{ t("public.theResortConfirmedYourRequest") }}
          {{
            canPay(booking)
              ? t("public.youCanNowTryTheDemoPayment")
              : booking.end <= dateAfter()
                ? t("public.yourStayHasEnded")
                : t("public.yourCheckinDateHasArrived")
          }}
        </p>
        <div v-if="booking.payment" class="payment-state">
          <strong>{{
            paymentNames[booking.payment.status] || booking.payment.status
          }}</strong
          ><span v-if="booking.payment.refundedAmount"
            >{{ t("public.refunded") }}
            {{ money(booking.payment.refundedAmount) }}</span
          ><span class="small muted">{{
            t("public.kaspiDemoNoRealMoneyIsUsed")
          }}</span>
        </div>
        <div class="guest-booking-actions">
          <RouterLink
            v-if="booking.payment?.receiptUrl"
            :to="booking.payment.receiptUrl"
            class="secondary button-link"
            >{{ t("public.demoReceipt") }}</RouterLink
          >
          <button
            v-if="canPay(booking)"
            class="primary"
            @click="paymentTarget = booking"
          >
            {{ t("public.payKaspiDemo") }}</button
          ><button
            v-if="canReview(booking)"
            class="secondary"
            @click="reviewTarget = booking"
          >
            {{ t("public.leaveAReview") }}</button
          ><span
            v-if="booking.reviewId || reviewed.has(booking.id)"
            class="small muted"
            >{{ t("public.reviewAlreadySubmitted") }}</span
          ><button
            v-if="canCancel(booking)"
            class="text-button danger"
            @click="openCancel(booking)"
          >
            {{ t("public.cancelBooking") }}
          </button>
        </div>
      </article>
      <DemoPayment
        v-if="paymentTarget"
        :booking="paymentTarget"
        @close="paymentTarget = null"
        @saved="paymentSaved"
      /><ReviewForm
        v-if="reviewTarget"
        :booking="reviewTarget"
        @close="reviewTarget = null"
        @saved="reviewSaved"
      />
      <Modal
        v-if="cancelTarget"
        :title="t('public.bookingCancellation')"
        :busy="busy || previewLoading"
        @close="cancelTarget = null"
        ><p class="confirm-text">
          {{ cancelTarget.resortName }} · {{ dateLabel(cancelTarget.start) }} —
          {{ dateLabel(cancelTarget.end) }}
        </p>
        <p v-if="previewLoading" role="status">
          {{ t("public.calculatingRefundTerms") }}
        </p>
        <template v-else-if="preview"
          ><div class="cancellation-quote">
            <div>
              <span>{{ t("public.paidInDemo") }}</span
              ><strong>{{ money(preview.paidAmount) }}</strong>
            </div>
            <div>
              <span>{{ t("public.refund") }} {{ preview.refundPercent }}%</span
              ><strong>{{ money(preview.refundAmount) }}</strong>
            </div>
          </div>
          <p class="confirm-text">
            {{
              preview.refundPercent === 0
                ? t("public.lessThan24HoursBeforeCheckinNoRefundIsAvailable")
                : t("public.yourCancellationDeadlineAllowsARefund", [
                    preview.refundPercent,
                  ])
            }}
          </p>
          <p class="field-help">
            {{ t("public.checkinTime") }} {{ checkinLabel(cancelTarget)
            }}{{
              t(
                "public.theServerRecalculatesTheDeadlineWhenCancellationIsConfirmedPaymentAndRefund",
              )
            }}
          </p></template
        >
        <p v-if="cancelError" class="form-error" role="alert">
          {{ cancelError }}
        </p>
        <div class="form-actions">
          <button
            class="secondary"
            :disabled="busy || previewLoading"
            @click="cancelTarget = null"
          >
            {{ t("public.keepBooking") }}</button
          ><button
            v-if="!preview && !previewLoading"
            class="secondary"
            @click="openCancel(cancelTarget)"
          >
            {{ t("public.recalculate") }}</button
          ><button
            class="danger-button"
            :disabled="busy || previewLoading || !preview"
            @click="cancel"
          >
            {{
              busy ? t("public.cancelling") : t("public.confirmCancellation")
            }}
          </button>
        </div></Modal
      >
    </main>
  </div>
</template>
