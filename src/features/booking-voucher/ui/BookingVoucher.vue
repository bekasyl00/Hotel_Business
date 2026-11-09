<script setup>
import { ref, computed, onBeforeUnmount, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { request, requestFile } from "@/shared/api";
import { apiBase } from "@/shared/config";
import { Modal } from "@/shared/ui";
import { money, dateLabel, timeLabel } from "@/shared/lib";
import { isNative, shareNativeFile } from "@/shared/native";
import { propertyToday } from "@/entities/booking";
import { canRecordOnsite } from "../model/access.js";
const props = defineProps({
  booking: { type: Object, required: true },
  allowOnsite: Boolean,
});
const emit = defineEmits(["saved"]);
const { t } = useI18n();
const open = ref(false),
  qrImage = ref(""),
  voucher = ref(null),
  busy = ref(false),
  error = ref(""),
  method = ref("cash"),
  received = ref(false),
  file = ref(null),
  fileUrl = ref(""),
  downloadLink = ref(null),
  notice = ref("");
let revision = 0;
const path = computed(
  () => `/bookings/${encodeURIComponent(props.booking.id)}/voucher`,
);
const canRecord = computed(() => {
  let today;
  try {
    today = propertyToday(voucher.value?.timeZone || "Asia/Almaty");
  } catch {
    return false;
  }
  return canRecordOnsite(
    voucher.value,
    props.booking,
    today,
    props.allowOnsite,
  );
});
function clearFile() {
  if (fileUrl.value) URL.revokeObjectURL(fileUrl.value);
  fileUrl.value = "";
  file.value = null;
}
function close() {
  revision++;
  open.value = false;
  clearFile();
}
async function show() {
  open.value = true;
  busy.value = true;
  error.value = "";
  notice.value = "";
  received.value = false;
  voucher.value = null;
  qrImage.value = "";
  clearFile();
  const current = ++revision;
  try {
    const result = await request("GET", path.value);
    if (current === revision) {
      voucher.value = result;
      if (result.scanCode) {
        const QRCode = (await import("qrcode")).default;
        const image = await QRCode.toDataURL(result.scanCode, {
          width: 280,
          margin: 3,
          errorCorrectionLevel: "M",
        });
        if (current === revision) qrImage.value = image;
      }
    }
  } catch (e) {
    if (current === revision) error.value = e.message;
  } finally {
    if (current === revision) busy.value = false;
  }
}
async function prepareFile() {
  if (file.value) return file.value;
  const current = revision;
  const blob = await requestFile(
    `${path.value}/pdf`,
    apiBase,
    "application/pdf",
  );
  if (current !== revision) return null;
  const number = String(voucher.value?.number || props.booking.id).replace(
    /[^a-zA-Z0-9_-]/g,
    "",
  );
  file.value = new File([blob], `tynys-booking-${number || "voucher"}.pdf`, {
    type: "application/pdf",
  });
  fileUrl.value = URL.createObjectURL(file.value);
  return file.value;
}
async function save(share = false) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const pdf = await prepareFile();
    if (!pdf) return;
    if (isNative()) {
      await shareNativeFile(pdf, t("common.voucher.title"));
      return;
    }
    if (share && navigator.share && navigator.canShare?.({ files: [pdf] })) {
      await navigator.share({ files: [pdf], title: t("common.voucher.title") });
    } else {
      await nextTick();
      downloadLink.value?.click();
    }
    notice.value = t("common.voucher.fileReady");
  } catch (e) {
    if (e.name !== "AbortError") error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function record() {
  if (busy.value || !canRecord.value || !received.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const booking = await request(
      "POST",
      `/bookings/${encodeURIComponent(props.booking.id)}/onsite-payment`,
      {
        version: props.booking.version,
        method: method.value,
        received: true,
      },
    );
    voucher.value = {
      ...voucher.value,
      onsitePayment: booking.onsitePayment || {
        status: "recorded",
        amount: voucher.value.paymentTerms.onsiteAmount,
        method: method.value,
      },
    };
    received.value = false;
    clearFile();
    notice.value = t("common.voucher.recorded");
    emit("saved", booking);
    voucher.value = await request("GET", path.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onBeforeUnmount(() => {
  revision++;
  clearFile();
});
</script>
<template>
  <button type="button" class="secondary" @click="show">
    {{ t("common.voucher.open") }}
  </button>
  <Modal
    v-if="open"
    :title="t('common.voucher.title')"
    :busy="busy"
    @close="close"
  >
    <div class="booking-voucher">
      <p v-if="busy && !voucher" role="status">
        {{ t("common.voucher.loading") }}
      </p>
      <template v-if="voucher">
        <div class="voucher-heading">
          <strong>{{ voucher.number }}</strong>
          <span class="voucher-status">{{
            t(
              voucher.status === "confirmed"
                ? "common.voucher.confirmed"
                : "common.voucher.cancelled",
            )
          }}</span>
        </div>
        <h3>{{ voucher.resortName }}</h3>
        <p>{{ voucher.roomName }} · № {{ voucher.unit }}</p>
        <dl class="voucher-facts">
          <div>
            <dt>{{ t("common.voucher.guest") }}</dt>
            <dd>{{ voucher.guestName }}</dd>
          </div>
          <div>
            <dt>{{ t("common.voucher.dates") }}</dt>
            <dd>
              {{ dateLabel(voucher.start) }} — {{ dateLabel(voucher.end) }}
            </dd>
          </div>
          <div>
            <dt>{{ t("common.voucher.checkIn") }}</dt>
            <dd>{{ voucher.checkInTime }} · {{ voucher.timeZone }}</dd>
          </div>
          <div>
            <dt>{{ t("common.voucher.guests") }}</dt>
            <dd>{{ voucher.guests }}</dd>
          </div>
          <div>
            <dt>{{ t("common.voucher.total") }}</dt>
            <dd>{{ money(voucher.paymentTerms.total) }}</dd>
          </div>
          <div>
            <dt>
              {{ t("common.voucher.online") }}
            </dt>
            <dd>
              {{ money(voucher.paymentTerms.onlineAmount) }} ·
              {{
                t(
                  voucher.onlinePaid
                    ? "common.voucher.paid"
                    : "common.voucher.unpaid",
                )
              }}
            </dd>
          </div>
          <div>
            <dt>{{ t("common.voucher.onsite") }}</dt>
            <dd>
              {{ money(voucher.paymentTerms.onsiteAmount) }} ·
              {{
                t(
                  voucher.onsitePayment?.status === "recorded"
                    ? "common.voucher.recordedShort"
                    : voucher.paymentTerms.onsiteAmount
                      ? "common.voucher.due"
                      : "common.voucher.notRequired",
                )
              }}
            </dd>
          </div>
          <div v-if="voucher.onsitePayment?.recordedAt">
            <dt>{{ t("common.voucher.recordedAt") }}</dt>
            <dd>{{ timeLabel(voucher.onsitePayment.recordedAt) }}</dd>
          </div>
        </dl>
        <p class="voucher-note">{{ t("common.voucher.explanation") }}</p>
        <figure v-if="qrImage" class="voucher-qr">
          <img
            :src="qrImage"
            width="240"
            height="240"
            :alt="t('common.arrival.qrAlt')"
          />
          <figcaption>
            <strong>{{ t("common.arrival.qrTitle") }}</strong
            ><span>{{ t("common.arrival.qrHint") }}</span>
          </figcaption>
        </figure>
        <div class="voucher-actions">
          <button
            type="button"
            class="primary"
            :disabled="busy"
            @click="save()"
          >
            {{
              busy ? t("common.voucher.loading") : t("common.voucher.download")
            }}
          </button>
          <button
            type="button"
            class="secondary"
            :disabled="busy"
            @click="save(true)"
          >
            {{ t("common.voucher.share") }}
          </button>
        </div>
        <div v-if="fileUrl" class="voucher-file">
          <a ref="downloadLink" :href="fileUrl" :download="file.name">{{
            t("common.voucher.download")
          }}</a>
          <a :href="fileUrl" target="_blank" rel="noopener">{{
            t("common.voucher.openPdf")
          }}</a>
        </div>
        <section
          v-if="
            allowOnsite &&
            voucher.status === 'confirmed' &&
            voucher.paymentTerms.onsiteAmount > 0 &&
            voucher.onsitePayment?.status !== 'recorded'
          "
          class="voucher-onsite"
        >
          <h4>{{ t("common.voucher.recordTitle") }}</h4>
          <p v-if="!canRecord" class="voucher-note">
            {{ t("common.voucher.recordDates") }}
          </p>
          <form v-else @submit.prevent="record">
            <label
              >{{ t("common.voucher.method") }}
              <select v-model="method" :disabled="busy">
                <option value="cash">{{ t("common.voucher.cash") }}</option>
                <option value="card">{{ t("common.voucher.card") }}</option>
              </select>
            </label>
            <label class="voucher-confirm"
              ><input
                v-model="received"
                type="checkbox"
                required
                :disabled="busy"
              /><span>{{
                t("common.voucher.receivedConfirmation", {
                  amount: money(voucher.paymentTerms.onsiteAmount),
                })
              }}</span></label
            >
            <p class="voucher-note">{{ t("common.voucher.recordHint") }}</p>
            <button type="submit" class="primary" :disabled="busy || !received">
              {{ t("common.voucher.record") }}
            </button>
          </form>
        </section>
      </template>
      <p v-if="notice" class="voucher-note" role="status">{{ notice }}</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button
        v-if="error && !voucher"
        type="button"
        class="secondary"
        @click="show"
      >
        {{ t("common.voucher.retry") }}
      </button>
    </div>
  </Modal>
</template>
<style scoped>
.booking-voucher {
  display: grid;
  gap: 0.9rem;
  min-width: 0;
}
.voucher-qr {
  display: flex;
  align-items: center;
  gap: 20px;
  margin: 4px 0;
  padding: 14px;
  border: 1px solid #dbe4d9;
  border-radius: 16px;
  background: #f8faf6;
}
.voucher-qr img {
  width: 180px;
  height: 180px;
  flex: none;
  max-width: 100%;
}
.voucher-qr figcaption {
  display: grid;
  gap: 10px;
  line-height: 1.5;
}
.voucher-qr figcaption span {
  font-size: 14px;
  color: #69786d;
}
@media (max-width: 520px) {
  .voucher-qr {
    flex-direction: column;
    text-align: center;
    gap: 8px;
  }
}
.booking-voucher h3,
.booking-voucher h4,
.booking-voucher p {
  margin: 0;
}
.booking-voucher h3 {
  font-size: 1.35rem;
}
.voucher-heading {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
  font-size: 0.8rem;
}
.voucher-heading > strong {
  overflow-wrap: anywhere;
}
.voucher-status {
  border-radius: 20px;
  background: #eef5e8;
  padding: 0.3rem 0.6rem;
}
.voucher-facts {
  display: grid;
  gap: 0.7rem;
  margin: 0;
  font-size: 0.85rem;
}
.voucher-facts > div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.voucher-facts dt {
  color: var(--muted, #68756b);
}
.voucher-facts dd {
  margin: 0;
  max-width: 65%;
  text-align: right;
  overflow-wrap: anywhere;
  font-weight: 600;
}
.voucher-note {
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--muted, #68756b);
}
.voucher-actions,
.voucher-file {
  display: flex;
  gap: 0.65rem;
  flex-wrap: wrap;
}
.voucher-actions button {
  flex: 1;
  min-height: 44px;
  font-size: 0.9rem;
}
.voucher-file a {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--forest, #245e4e);
}
.voucher-onsite {
  border-top: 1px solid #dce4df;
  padding-top: 1rem;
  display: grid;
  gap: 0.75rem;
}
.voucher-onsite form {
  display: grid;
  gap: 0.8rem;
}
.voucher-onsite label {
  display: grid;
  gap: 0.4rem;
  font-size: 0.85rem;
}
.voucher-onsite .voucher-confirm {
  display: flex;
  align-items: start;
  gap: 0.7rem;
  cursor: pointer;
}
.voucher-confirm input {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  margin: 0;
}
</style>
