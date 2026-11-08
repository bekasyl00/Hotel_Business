<script setup>
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { occupancyState } from "@/entities/booking";
import { BookingDocuments } from "@/features/booking-documents";
import { DocumentGuests } from "@/features/document-guests";
import { BookingVoucher, canOpenVoucher } from "@/features/booking-voucher";
import { isBankProvider } from "@/features/pay-booking";
import { isDemo } from "@/shared/config";
import { Modal } from "@/shared/ui";
import { money, dateLabel, timeLabel, statusNames } from "@/shared/lib";
const props = defineProps({
  booking: Object,
  audit: Array,
  busy: Boolean,
  readOnly: Boolean,
  canViewHistory: Boolean,
  canCheckIn: Boolean,
  canPay: Boolean,
  error: String,
});
const emit = defineEmits(["close", "action", "notes", "saved"]);
const { t } = useI18n();
const tab = ref("main"),
  documentGuestsBusy = ref(false),
  notes = ref(props.booking.staffNotes || "");
const tabs = computed(() =>
  props.readOnly
    ? ["main", "guests", "calculation", "payment"]
    : [
        "main",
        "guests",
        "calculation",
        "payment",
        "notes",
        ...(props.canViewHistory ? ["history"] : []),
      ],
);
const state = computed(() => occupancyState(props.booking));
const history = computed(() =>
  (props.audit || []).filter((a) => a.entityId === props.booking.id),
);
watch(
  () => props.canViewHistory,
  (allowed) => {
    if (!allowed && tab.value === "history") tab.value = "main";
  },
);
watch(
  () => props.booking.staffNotes,
  (value) => {
    notes.value = value || "";
  },
);
const actionName = (action) =>
  ({
    create: t("staff.created"),
    notes: t("staff.board.notesSaved"),
    "check-in": t("staff.checkedIn"),
    "check-out": t("staff.checkedOut"),
    payment_confirmed: t("common.checkout.paymentBooked"),
    payment_expired: t("common.status.expired"),
    cancelled: t("staff.cancelled"),
    demo_payment: t("staff.demoPayment"),
    demo_refund: t("staff.demoRefund"),
  })[action] || action;
</script>
<template>
  <Modal
    wide
    :title="t('staff.board.cardTitle', { room: booking.unit })"
    :busy="busy || documentGuestsBusy"
    @close="emit('close')"
  >
    <div class="stay-card-intro">
      <div>
        <h3>{{ booking.guestLabel }}</h3>
        <p>{{ booking.roomName }} · #{{ booking.id.slice(0, 8) }}</p>
      </div>
      <span :class="['stay-chip', state]">{{
        state === "closed"
          ? statusNames[booking.status]
          : t(`staff.board.${state}`)
      }}</span>
    </div>
    <nav class="stay-tabs" :aria-label="t('staff.board.sections')">
      <button
        v-for="key in tabs"
        :key="key"
        :disabled="documentGuestsBusy"
        :aria-current="tab === key ? 'page' : undefined"
        @click="tab = key"
      >
        {{ t(`staff.board.${key}`) }}
      </button>
    </nav>
    <section class="stay-card-body">
      <template v-if="tab === 'main'">
        <div class="stay-dates">
          <div>
            <small>{{ t("staff.arrival") }}</small
            ><strong>{{ dateLabel(booking.start) }}</strong
            ><span>{{
              booking.cancellationPolicy?.checkinAt
                ? timeLabel(booking.cancellationPolicy.checkinAt)
                : "—"
            }}</span>
          </div>
          <span>→</span>
          <div>
            <small>{{ t("staff.departure") }}</small
            ><strong>{{ dateLabel(booking.end) }}</strong
            ><span>{{ t("staff.board.nights", { n: booking.nights }) }}</span>
          </div>
        </div>
        <dl class="stay-facts">
          <div>
            <dt>{{ t("staff.created") }}</dt>
            <dd>{{ timeLabel(booking.createdAt) }}</dd>
          </div>
          <div>
            <dt>{{ t("staff.guests") }}</dt>
            <dd>{{ booking.guests }}</dd>
          </div>
          <div>
            <dt>{{ t("staff.amount") }}</dt>
            <dd>{{ money(booking.paymentTerms?.total ?? booking.total) }}</dd>
          </div>
          <div>
            <dt>{{ t("staff.board.source") }}</dt>
            <dd>
              {{
                t(booking.source === "staff" ? "staff.manual" : "staff.website")
              }}
            </dd>
          </div>
          <div v-if="booking.checkedInAt">
            <dt>{{ t("staff.actualArrival") }}</dt>
            <dd>{{ timeLabel(booking.checkedInAt) }}</dd>
          </div>
          <div v-if="booking.checkedOutAt">
            <dt>{{ t("staff.actualDeparture") }}</dt>
            <dd>{{ timeLabel(booking.checkedOutAt) }}</dd>
          </div>
        </dl>
        <p
          v-if="booking.status === 'pending' && booking.holdExpiresAt"
          class="field-help"
        >
          {{
            t("common.checkout.payBefore", {
              date: timeLabel(booking.holdExpiresAt),
            })
          }}
        </p>
        <p v-if="booking.staffNotes" class="stay-note-text">
          {{ booking.staffNotes }}
        </p>
      </template>
      <template v-else-if="tab === 'guests'"
        ><h3>{{ t("staff.board.leadGuest") }}</h3>
        <p>{{ booking.guestLabel }}</p>
        <p v-if="booking.guestPhone">{{ booking.guestPhone }}</p>
        <p>{{ t("staff.guestCount", { count: booking.guests }) }}</p>
        <p v-if="booking.childrenAges?.length">
          {{ t("staff.board.ages") }}: {{ booking.childrenAges.join(", ") }}
        </p>
        <RouterLink
          v-if="booking.guestProfileId && !readOnly"
          :to="`/staff/guests/${booking.guestProfileId}`"
          >{{ t("staff.guestProfile") }}</RouterLink
        >
        <DocumentGuests
          :booking-id="booking.id"
          :guest-name="booking.guestLabel"
          @busy="documentGuestsBusy = $event"
        />
      </template>
      <template v-else-if="tab === 'calculation'"
        ><p>{{ t("staff.board.frozenPrice") }}</p>
        <p v-if="booking.tariffName" class="field-help">
          {{ t("staff.board.legacyTerms") }}: {{ booking.tariffName }}
        </p>
        <dl class="stay-facts">
          <div v-for="line in booking.nightlyBreakdown || []" :key="line.date">
            <dt>
              {{ dateLabel(line.date) }}<small>{{ line.periodLabel }}</small>
            </dt>
            <dd>{{ money(line.nightly) }}</dd>
          </div>
          <div>
            <dt>{{ t("staff.amount") }}</dt>
            <dd>
              <strong>{{
                money(booking.paymentTerms?.total ?? booking.total)
              }}</strong>
            </dd>
          </div>
          <div v-if="booking.paymentTerms?.version === 1">
            <dt>{{ t("common.payment.onlineCommission") }}</dt>
            <dd>{{ money(booking.paymentTerms.onlineAmount) }}</dd>
          </div>
          <div v-if="booking.paymentTerms?.version === 1">
            <dt>{{ t("common.payment.onsiteAmount") }}</dt>
            <dd>{{ money(booking.paymentTerms.onsiteAmount) }}</dd>
          </div>
          <div
            v-if="
              booking.commissionTerms && booking.paymentTerms?.version !== 1
            "
          >
            <dt>{{ t("common.checkout.commissionEstimate") }}</dt>
            <dd>
              {{
                booking.commissionTerms.amount == null
                  ? t("common.checkout.notConfigured")
                  : money(booking.commissionTerms.amount)
              }}
            </dd>
          </div>
          <div
            v-if="
              booking.commissionTerms?.resortAmount != null &&
              !booking.paymentTerms
            "
          >
            <dt>{{ t("common.checkout.resortEstimate") }}</dt>
            <dd>{{ money(booking.commissionTerms.resortAmount) }}</dd>
          </div>
        </dl>
        <p
          v-if="booking.payment?.refundedAmount && booking.commissionTerms"
          class="field-help"
        >
          {{ t("common.checkout.refundReconciliation") }}
        </p></template
      >
      <template v-else-if="tab === 'payment'"
        ><h3>
          {{
            isBankProvider(booking.payment?.provider)
              ? t(`common.payment.states.${booking.payment.checkoutStatus}`)
              : booking.payment?.status === "paid"
                ? t("staff.demoPaid")
                : booking.payment?.status === "failed"
                  ? t("staff.demoFailed")
                  : booking.payment?.status === "refunded"
                    ? t("staff.demoRefunded")
                    : t("staff.board.unpaid")
          }}
        </h3>
        <p>
          {{ t("staff.amount") }}:
          {{ money(booking.paymentTerms?.total ?? booking.total) }}
        </p>
        <p v-if="isBankProvider(booking.payment?.provider)" class="field-help">
          {{
            t(
              booking.payment.provider === "xpayment"
                ? "common.payment.kaspiXPayment"
                : "common.payment.halykSandbox",
            )
          }}
        </p>
        <p
          v-if="
            isBankProvider(booking.payment?.provider) &&
            booking.payment.refundStatus
          "
        >
          {{ t(`common.payment.refunds.${booking.payment.refundStatus}`) }}
        </p>
        <p v-if="booking.payment?.refundedAmount">
          {{ t("public.refunded") }}:
          {{ money(booking.payment.refundedAmount) }}
        </p>
        <RouterLink
          v-if="booking.payment?.receiptUrl && !readOnly"
          class="secondary receipt-link"
          :to="booking.payment.receiptUrl"
          >{{ t("staff.openReceipt") }}</RouterLink
        >
        <p class="field-help">
          {{
            t(
              isDemo
                ? "staff.board.demoPaymentHint"
                : "common.payment.verificationHint",
            )
          }}
        </p></template
      >
      <form v-else-if="tab === 'notes'" @submit.prevent="emit('notes', notes)">
        <label class="stay-notes-label"
          >{{ t("staff.board.notes")
          }}<textarea
            v-model="notes"
            rows="6"
            maxlength="2000"
            :disabled="busy || documentGuestsBusy"
          ></textarea>
        </label>
        <p class="field-help">
          {{ t("staff.board.notesHint") }} · {{ notes.length }}/2000
        </p>
        <button
          class="primary"
          :disabled="
            busy || documentGuestsBusy || notes === (booking.staffNotes || '')
          "
        >
          {{ t("staff.board.saveNotes") }}
        </button>
      </form>
      <template v-else-if="tab === 'history' && canViewHistory"
        ><p class="field-help">{{ t("staff.board.historyHint") }}</p>
        <ol class="stay-history">
          <li v-for="entry in history" :key="entry.id">
            <strong>{{ actionName(entry.action) }}</strong
            ><small>{{ timeLabel(entry.at) }} · {{ entry.actor }}</small>
          </li>
        </ol>
        <p v-if="!history.length">{{ t("staff.noRecords") }}</p></template
      >
    </section>
    <p v-if="error" role="alert" class="form-error">{{ error }}</p>
    <div v-if="!readOnly" class="stay-card-actions">
      <button
        v-if="canPay"
        class="primary"
        :disabled="busy || documentGuestsBusy"
        @click="emit('action', 'pay')"
      >
        {{ t(isDemo ? "staff.demoPayment" : "common.payment.title") }}</button
      ><button
        v-else-if="
          booking.source === 'staff' &&
          isBankProvider(booking.payment?.provider)
        "
        class="secondary"
        :disabled="busy || documentGuestsBusy"
        @click="emit('action', 'pay')"
      >
        {{ t("common.payment.details") }}</button
      ><button
        v-if="canCheckIn"
        class="primary"
        :disabled="busy || documentGuestsBusy"
        @click="emit('action', 'check-in')"
      >
        {{ t("staff.checkIn") }}</button
      ><button
        v-if="booking.stayStatus === 'in_house'"
        class="primary"
        :disabled="busy || documentGuestsBusy"
        @click="emit('action', 'check-out')"
      >
        {{ t("staff.checkOut") }}</button
      ><button
        v-if="
          ['pending', 'confirmed'].includes(booking.status) &&
          !booking.checkedInAt
        "
        class="text-button danger"
        :disabled="busy || documentGuestsBusy"
        @click="emit('action', 'cancel')"
      >
        {{ t("staff.cancelBookingTitle") }}</button
      ><button
        class="secondary"
        :disabled="busy || documentGuestsBusy"
        @click="emit('close')"
      >
        {{ t("staff.close") }}
      </button>
    </div>
    <BookingVoucher
      v-if="!isDemo && canOpenVoucher(booking)"
      :booking="booking"
      :allow-onsite="!readOnly"
      @saved="emit('saved', $event)"
    />
    <BookingDocuments :booking-id="booking.id" />
  </Modal>
</template>
