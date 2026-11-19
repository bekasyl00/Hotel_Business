<script setup>
import { GuestIdentity } from "@/shared/ui";
import { useI18n } from "vue-i18n";
import { money, dateLabel, timeLabel, statusNames } from "@/shared/lib";
import { isBankProvider } from "@/features/pay-booking";
import { isDemo } from "@/shared/config";
const { t } = useI18n();
defineProps([
  "filteredBookings",
  "isAccountant",
  "busy",
  "canPayStaff",
  "canCheckIn",
  "stayNames",
]);
const emit = defineEmits(["focus", "pay", "cancel", "stay"]);
</script>
<template>
  <div
    class="table-scroll"
    tabindex="0"
    role="region"
    :aria-label="t('staff.dataTable')"
  >
    <table class="workspace-table">
      <thead>
        <tr>
          <th>{{ t("staff.bookingGuest") }}</th>
          <th>{{ t("staff.room") }}</th>
          <th>{{ t("staff.dates") }}</th>
          <th>{{ t("staff.amount") }}</th>
          <th>{{ t("staff.status") }}</th>
          <th>{{ t("staff.action") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in filteredBookings" :key="b.id">
          <td :data-label="t('staff.bookingGuest')">
            <GuestIdentity :name="b.guestLabel" :photo="isAccountant ? null : b.guestAvatarUrl" style="--avatar-size: 30px">
            <RouterLink
              v-if="b.guestProfileId && !isAccountant"
              :to="`/staff/guests/${b.guestProfileId}`"
              ><strong>{{ b.guestLabel }}</strong></RouterLink
            >
            <button v-else class="text-button" @click="emit('focus', b.id)">
              <strong>{{ b.guestLabel }}</strong></button
            ><small v-if="b.guestPhone">{{ b.guestPhone }}</small
            ><small
              >#{{ b.id.slice(0, 8) }} ·
              {{
                b.source === "staff" ? t("staff.manual") : t("staff.website")
              }}</small
            >
            </GuestIdentity>
          </td>
          <td :data-label="t('staff.room')">
            № {{ b.unit }} · {{ b.roomName
            }}<small>{{ t("staff.guestCount", { count: b.guests }) }}</small>
          </td>
          <td :data-label="t('staff.dates')">
            {{ dateLabel(b.start)
            }}<small>{{
              t("staff.untilDate", { date: dateLabel(b.end) })
            }}</small>
          </td>
          <td :data-label="t('staff.amount')" class="numeric">
            {{ money(b.paymentTerms?.total ?? b.total)
            }}<small v-if="b.payment"
              >{{
                isBankProvider(b.payment.provider)
                  ? t(`common.payment.states.${b.payment.checkoutStatus}`)
                  : b.payment.status === "paid"
                    ? t("staff.demoPaid")
                    : ["failed", "creating", "pending"].includes(
                          b.payment.status,
                        )
                      ? t("staff.demoFailed")
                      : t("staff.demoRefunded")
              }}<span v-if="b.payment.refundedAmount">
                {{ money(b.payment.refundedAmount) }}</span
              ></small
            >
            <RouterLink
              v-if="b.payment?.receiptUrl && !isAccountant"
              class="receipt-link"
              :to="b.payment.receiptUrl"
              >{{ t("staff.openReceipt") }}</RouterLink
            >
          </td>
          <td :data-label="t('staff.status')">
            <span :class="['status-pill', b.status]">{{
              statusNames[b.status]
            }}</span>
            <small v-if="b.status === 'confirmed'">{{
              stayNames[b.stayStatus || "not_arrived"]
            }}</small>
            <small v-if="b.status === 'pending' && b.holdExpiresAt">{{
              t("common.checkout.payBefore", {
                date: timeLabel(b.holdExpiresAt),
              })
            }}</small>
            <small v-if="b.commissionTerms"
              >{{ t("common.checkout.commissionEstimate") }}:
              {{
                b.commissionTerms.amount == null
                  ? t("common.checkout.notConfigured")
                  : money(b.commissionTerms.amount)
              }}</small
            >
            <small v-if="b.commissionTerms?.resortAmount != null"
              >{{ t("common.checkout.resortEstimate") }}:
              {{ money(b.commissionTerms.resortAmount) }}</small
            >
            <small v-if="b.commissionTerms && b.payment?.refundedAmount">{{
              t("common.checkout.refundReconciliation")
            }}</small>
            <small v-if="b.checkedInAt">{{
              t("staff.arrivalAt", {
                date: timeLabel(b.checkedInAt),
              })
            }}</small>
            <small v-if="b.checkedOutAt">{{
              t("staff.departureAt", {
                date: timeLabel(b.checkedOutAt),
              })
            }}</small>
          </td>
          <td :data-label="t('staff.action')">
            <div
              v-if="!isAccountant && b.status === 'pending'"
              class="row-actions"
            >
              <button
                v-if="canPayStaff(b)"
                class="text-button"
                @click="emit('pay', b)"
              >
                {{
                  t(isDemo ? "common.checkout.demoPay" : "common.payment.title")
                }}
              </button>
              <button
                class="text-button danger"
                :disabled="busy"
                @click="emit('cancel', b)"
              >
                {{ t("staff.cancelBooking") }}
              </button>
            </div>
            <div
              v-else-if="!isAccountant && b.status === 'confirmed'"
              class="row-actions"
            >
              <button
                v-if="canPayStaff(b)"
                class="text-button"
                @click="emit('pay', b)"
              >
                {{
                  t(isDemo ? "common.checkout.demoPay" : "common.payment.title")
                }}
              </button>
              <button
                v-if="canCheckIn(b)"
                class="text-button"
                :disabled="busy"
                @click="emit('stay', b, 'check-in')"
              >
                {{ t("staff.checkIn") }}
              </button>
              <button
                v-if="b.stayStatus === 'in_house'"
                class="text-button"
                :disabled="busy"
                @click="emit('stay', b, 'check-out')"
              >
                {{ t("staff.checkOut") }}
              </button>
              <button
                v-if="!b.checkedInAt"
                class="text-button danger"
                :disabled="busy"
                @click="emit('cancel', b)"
              >
                {{ t("staff.cancelBooking") }}
              </button>
            </div>
            <span v-else>—</span>
            <button
              v-if="
                b.source === 'staff' &&
                isBankProvider(b.payment?.provider) &&
                !canPayStaff(b)
              "
              class="text-button"
              @click="emit('pay', b)"
            >
              {{ t("common.payment.details") }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
