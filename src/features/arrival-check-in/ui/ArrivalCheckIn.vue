<script setup>
import { ref, computed, nextTick, onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useBookingStore } from "@/entities/booking";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
import { money, dateLabel } from "@/shared/lib";
import { createQrScanner } from "../model/scanner.js";
const props = defineProps({ booking: Object, disabled: Boolean });
const emit = defineEmits(["saved"]);
const { t } = useI18n();
const route = useRoute(),
  bookings = useBookingStore();
const open = ref(false),
  camera = ref(false),
  video = ref(null),
  code = ref(""),
  result = ref(null),
  busy = ref(false),
  received = ref(false),
  method = ref("cash"),
  error = ref(""),
  done = ref(false);
let scanner = null,
  revision = 0;
const due = computed(() =>
  result.value?.voucher.onsitePayment?.status === "recorded"
    ? 0
    : result.value?.voucher.paymentTerms.onsiteAmount || 0,
);
function stopCamera() {
  scanner?.stop();
  scanner = null;
  camera.value = false;
}
function close() {
  revision++;
  stopCamera();
  open.value = false;
  result.value = null;
  code.value = "";
}
async function resolve(value) {
  stopCamera();
  const current = ++revision;
  busy.value = true;
  error.value = "";
  result.value = null;
  received.value = false;
  done.value = false;
  try {
    const data = await request("POST", "/staff/arrivals/resolve", {
      code: value.trim(),
    });
    if (current === revision) result.value = data;
  } catch (e) {
    if (current === revision) error.value = e.message;
  } finally {
    if (current === revision) busy.value = false;
  }
}
async function startCamera() {
  stopCamera();
  result.value = null;
  error.value = "";
  done.value = false;
  camera.value = true;
  const current = ++revision;
  await nextTick();
  if (current !== revision || !video.value) return;
  try {
    scanner = await createQrScanner(
      video.value,
      (value) => {
        if (current === revision) resolve(value);
      },
      () => {
        if (current !== revision) return;
        camera.value = false;
        error.value = t("common.arrival.cameraError");
      },
    );
    if (current !== revision) scanner?.stop();
  } catch {
    camera.value = false;
    error.value = t("common.arrival.cameraError");
  }
}
async function show() {
  open.value = true;
  busy.value = false;
  done.value = false;
  code.value = "";
  error.value = "";
  if (props.booking) await resolve(props.booking.id);
  else await startCamera();
}
async function accept() {
  if (
    busy.value ||
    result.value?.state !== "ready" ||
    (due.value > 0 && !received.value)
  )
    return;
  busy.value = true;
  error.value = "";
  const current = revision,
    bookingId = result.value.booking.id;
  try {
    const booking = await request(
      "POST",
      `/bookings/${encodeURIComponent(bookingId)}/accept-arrival`,
      {
        version: result.value.booking.version,
        method: method.value,
        received: received.value,
      },
    );
    const index = bookings.items.findIndex((item) => item.id === booking.id);
    if (index >= 0) bookings.items[index] = booking;
    if (current !== revision || result.value?.booking.id !== bookingId) return;
    done.value = true;
    result.value.state = "accepted";
    result.value.booking = booking;
    if (booking.onsitePayment)
      result.value.voucher.onsitePayment = booking.onsitePayment;
    emit("saved", booking);
  } catch (e) {
    if (current === revision) error.value = e.message;
  } finally {
    if (current === revision) busy.value = false;
  }
}
watch(() => route.fullPath, close);
function hideCamera() {
  if (document.hidden) stopCamera();
}
if (typeof document !== "undefined")
  document.addEventListener("visibilitychange", hideCamera);
onBeforeUnmount(() => {
  close();
  document.removeEventListener("visibilitychange", hideCamera);
});
</script>
<template>
  <button
    type="button"
    :class="booking ? 'primary' : 'arrival-trigger'"
    :disabled="disabled"
    @click="show"
  >
    <span aria-hidden="true">▦</span>
    {{ t(booking ? "common.arrival.acceptTitle" : "common.arrival.scan") }}
  </button>
  <Modal
    v-if="open"
    :title="t('common.arrival.title')"
    :busy="busy"
    @close="close"
  >
    <div class="arrival-flow">
      <template v-if="!result">
        <div v-if="camera" class="arrival-camera">
          <video
            ref="video"
            autoplay
            muted
            playsinline
            :aria-label="t('common.arrival.camera')"
          />
          <div class="arrival-target" aria-hidden="true"></div>
          <p>{{ t("common.arrival.aim") }}</p>
        </div>
        <button
          v-if="!camera"
          class="secondary"
          :disabled="busy"
          @click="startCamera"
        >
          {{ t("common.arrival.startCamera") }}
        </button>
        <button v-else class="text-button" @click="stopCamera">
          {{ t("common.arrival.stopCamera") }}
        </button>
        <form class="arrival-manual" @submit.prevent="resolve(code)">
          <label
            >{{ t("common.arrival.number")
            }}<input
              v-model="code"
              maxlength="256"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              placeholder="TYNYS-…"
              :disabled="busy"
              required
          /></label>
          <button class="secondary" :disabled="busy || !code.trim()">
            {{ t("common.arrival.find") }}
          </button>
        </form>
      </template>
      <template v-else>
        <div class="arrival-summary">
          <span class="eyebrow">{{ result.voucher.resortName }}</span>
          <h3>{{ result.voucher.guestName }}</h3>
          <p>{{ result.voucher.roomName }} · № {{ result.voucher.unit }}</p>
          <p>
            {{ dateLabel(result.voucher.start) }} —
            {{ dateLabel(result.voucher.end) }} ·
            {{ t("common.arrival.guests", { count: result.voucher.guests }) }}
          </p>
        </div>
        <dl class="arrival-money">
          <div>
            <dt>{{ t("common.arrival.total") }}</dt>
            <dd>{{ money(result.voucher.paymentTerms.total) }}</dd>
          </div>
          <div>
            <dt>{{ t("common.arrival.onlinePaid") }}</dt>
            <dd>{{ money(result.voucher.onlinePaid) }}</dd>
          </div>
          <div>
            <dt>{{ t("common.arrival.onsite") }}</dt>
            <dd>
              {{ money(result.voucher.paymentTerms.onsiteAmount)
              }}<small
                v-if="result.voucher.onsitePayment.status === 'recorded'"
                >{{ t("common.arrival.recorded") }}</small
              >
            </dd>
          </div>
        </dl>
        <p v-if="result.state !== 'ready'" class="arrival-state" role="status">
          {{ t(`common.arrival.state.${result.state}`) }}
        </p>
        <form v-if="result.state === 'ready'" @submit.prevent="accept">
          <template v-if="due > 0"
            ><label
              >{{ t("common.arrival.method")
              }}<select v-model="method" :disabled="busy">
                <option value="cash">{{ t("common.arrival.cash") }}</option>
                <option value="card">{{ t("common.arrival.card") }}</option>
              </select></label
            ><label class="arrival-ack"
              ><input
                v-model="received"
                type="checkbox"
                :disabled="busy"
                required
              /><span>{{
                t("common.arrival.received", { amount: money(due) })
              }}</span></label
            ></template
          >
          <p class="arrival-hint">{{ t("common.arrival.confirmHint") }}</p>
          <button class="primary" :disabled="busy || (due > 0 && !received)">
            {{ t("common.arrival.confirm") }}
          </button>
        </form>
        <button
          class="secondary"
          :disabled="busy"
          @click="props.booking ? resolve(props.booking.id) : startCamera()"
        >
          {{ t(done ? "common.arrival.next" : "common.arrival.retry") }}
        </button>
      </template>
      <p v-if="busy" role="status">{{ t("common.arrival.loading") }}</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    </div>
  </Modal>
</template>
<style scoped>
.arrival-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid #cbd6cb;
  background: #edf3e8;
  color: #255b4c;
  border-radius: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.arrival-trigger span {
  font-size: 22px;
}
.arrival-flow {
  display: grid;
  gap: 18px;
  min-width: 0;
}
.arrival-camera {
  position: relative;
  background: #152a23;
  border-radius: 18px;
  overflow: hidden;
  aspect-ratio: 4/3;
}
.arrival-camera video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.arrival-camera p {
  position: absolute;
  bottom: 10px;
  left: 10px;
  right: 10px;
  color: white;
  text-align: center;
  background: #14251dbb;
  border-radius: 8px;
  padding: 8px;
}
.arrival-target {
  position: absolute;
  width: 55%;
  aspect-ratio: 1;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 3px solid white;
  border-radius: 18px;
  box-shadow: 0 0 0 200px #0004;
}
.arrival-manual {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  gap: 10px;
}
.arrival-flow label {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.arrival-flow input:not([type="checkbox"]),
.arrival-flow select {
  width: 100%;
  min-width: 0;
  min-height: 46px;
  border: 1px solid #cbd6cb;
  border-radius: 10px;
  padding: 10px 12px;
  font: inherit;
  color: inherit;
  background: white;
}
.arrival-summary h3 {
  margin: 8px 0;
  font-size: 26px;
}
.arrival-summary p {
  margin: 5px 0;
}
.arrival-money {
  display: grid;
  gap: 12px;
  margin: 0;
  border-block: 1px solid #dbe3d9;
  padding: 18px 0;
}
.arrival-money > div {
  display: flex;
  justify-content: space-between;
  gap: 15px;
}
.arrival-money dd {
  margin: 0;
  text-align: right;
  font-weight: 700;
}
.arrival-money small {
  display: block;
  font-weight: 400;
}
.arrival-flow .arrival-ack {
  display: flex;
  align-items: start;
  gap: 12px;
  margin-top: 18px;
}
.arrival-ack input {
  flex: none;
  width: 22px;
  height: 22px;
  margin: 2px 0;
}
.arrival-hint {
  font-size: 14px;
  color: #69786d;
}
.arrival-state {
  padding: 16px;
  background: #edf3e8;
  border-radius: 12px;
}
.arrival-flow form > .primary {
  width: 100%;
}
@media (max-width: 520px) {
  .arrival-manual {
    grid-template-columns: 1fr;
  }
  .arrival-trigger {
    padding: 8px 10px;
    font-size: 13px;
  }
}
</style>
