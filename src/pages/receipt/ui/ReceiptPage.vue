<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { PublicHeader } from "@/widgets/public-header";
import { ReceiptActions } from "@/features/payment-receipt";
import { request } from "@/shared/api";
import { isStaffSurface, isStaffApp } from "@/shared/config";
import { money, dateLabel, timestampLabel } from "@/shared/lib";
const route = useRoute(),
  data = ref(null),
  loading = ref(true),
  error = ref("");
const receipt = computed(() => data.value?.receipt);
let generation = 0;
async function load() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  data.value = null;
  try {
    const value = await request(
      "GET",
      `/receipts/${encodeURIComponent(route.params.id)}`,
    );
    if (run === generation) data.value = value;
  } catch (e) {
    if (run === generation)
      error.value =
        e.status === 404 || e.status === 403
          ? t("public.theReceiptWasNotFoundOrIsUnavailableInThisSession")
          : e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
watch(() => route.params.id, load, { immediate: true });
</script>
<template>
  <div class="public-site">
    <PublicHeader v-if="!isStaffApp" />
    <main id="public-main" class="profile-main receipt-main">
      <RouterLink
        class="profile-back"
        :to="isStaffSurface ? '/staff/bookings' : '/profile'"
        >{{
          t(
            isStaffSurface
              ? "public.goToStaffBookings"
              : "public.myProfileAndHistory",
          )
        }}</RouterLink
      >
      <div v-if="loading" class="profile-feedback" role="status">
        {{ t("public.loadingReceipt") }}
      </div>
      <div v-else-if="error" class="profile-feedback" role="alert">
        <h1>{{ t("public.receiptUnavailable") }}</h1>
        <p>{{ error }}</p>
        <button class="secondary" @click="load">{{ t("public.retry") }}</button
        ><RouterLink :to="isStaffSurface ? '/staff/bookings' : '/bookings'">{{
          t(isStaffSurface ? "public.goToStaffBookings" : "public.myBookings")
        }}</RouterLink>
      </div>
      <template v-else-if="receipt"
        ><header class="profile-heading">
          <div>
            <span class="eyebrow">{{ t("public.paymentHistory") }}</span>
            <h1>{{ t("public.demoReceiptInReceiptPage") }}</h1>
            <p>
              № {{ receipt.number }} ·
              {{ timestampLabel(receipt.issuedAt, receipt.timeZone) }}
            </p>
          </div>
        </header>
        <div class="receipt-demo-warning">
          <strong>{{ t("public.notAKaspiReceipt") }}</strong>
          <p>
            {{
              t(
                "public.noRealMoneyWasChargedThisPaymentWasSimulatedAnActualPaymentprovider",
              )
            }}
          </p>
        </div>
        <p v-if="receipt.legacySnapshot" class="public-session-note">
          {{
            t(
              "public.thisReceiptWasReconstructedFromAnOlderDemoSomeDetailsReflectWhen",
            )
          }}
        </p>
        <article class="receipt-sheet">
          <div class="receipt-sheet-heading">
            <strong class="brand">{{ t("public.tynys") }}</strong
            ><span>{{ t("public.demonstration") }}</span>
          </div>
          <h2>{{ receipt.resortName }}</h2>
          <p class="field-help">{{ receipt.resortAddress }}</p>
          <dl class="receipt-facts">
            <div>
              <dt>{{ t("public.guest") }}</dt>
              <dd>{{ receipt.guestLabel || t("public.websiteGuest") }}</dd>
            </div>
            <div>
              <dt>{{ t("public.roomInReceiptPage") }}</dt>
              <dd>№ {{ receipt.unit }} · {{ receipt.roomName }}</dd>
            </div>
            <div>
              <dt>{{ t("public.dates") }}</dt>
              <dd>
                {{ dateLabel(receipt.start) }} — {{ dateLabel(receipt.end) }}
              </dd>
            </div>
            <div>
              <dt>{{ t("public.checkinTimeInReceiptPage") }}</dt>
              <dd>
                {{ timestampLabel(receipt.checkinAt, receipt.timeZone) }}
              </dd>
            </div>
            <div>
              <dt>{{ t("public.guestsNights") }}</dt>
              <dd>{{ receipt.guests }} / {{ receipt.nights }}</dd>
            </div>
            <div>
              <dt>{{ t("public.rate") }}</dt>
              <dd>{{ receipt.tariffName }}</dd>
            </div>
            <div v-if="receipt.discountPercent">
              <dt>{{ t("public.discountInReceiptPage") }}</dt>
              <dd>{{ receipt.discountPercent }}%</dd>
            </div>
            <div v-if="receipt.nightly != null">
              <dt>{{ t("public.nightlyPrice") }}</dt>
              <dd>{{ money(receipt.nightly) }}</dd>
            </div>
          </dl>
          <details
            v-if="receipt.nightlyBreakdown?.length"
            class="price-breakdown"
          >
            <summary>{{ t("common.pricing.breakdown") }}</summary>
            <dl>
              <div v-for="line in receipt.nightlyBreakdown" :key="line.date">
                <dt>{{ line.date }}</dt>
                <dd>{{ money(line.nightly) }}</dd>
              </div>
            </dl>
          </details>
          <div class="receipt-total">
            <span>{{ t("public.paidInDemonstration") }}</span
            ><strong>{{ money(receipt.total) }}</strong>
          </div>
          <div v-if="data.refund" class="receipt-refund">
            <h3>{{ t("public.demoRefund") }}</h3>
            <p>{{ money(data.refund.amount) }} · {{ data.refund.percent }}%</p>
            <p class="small muted">
              {{
                data.refund.createdAt
                  ? timestampLabel(data.refund.createdAt, receipt.timeZone)
                  : t("public.theOldDemoDidNotRecordARefundDate")
              }}
            </p>
          </div>
          <dl class="receipt-identifiers">
            <div>
              <dt>{{ t("public.booking") }}</dt>
              <dd>{{ receipt.bookingId }}</dd>
            </div>
            <div>
              <dt>{{ t("public.payment") }}</dt>
              <dd>{{ receipt.paymentId }}</dd>
            </div>
          </dl>
          <p class="field-help">
            {{ t("public.thisDocumentDoesNotConfirmARealPaymentAndIsNotA") }}
          </p>
        </article>
        <ReceiptActions :key="receipt.paymentId" :bundle="data" />
        <p class="public-data-note">
          {{
            t(
              "public.theReceiptIsAvailableToTheBookingOwnerAndAuthorisedResortStaff",
            )
          }}
        </p></template
      >
    </main>
  </div>
</template>
