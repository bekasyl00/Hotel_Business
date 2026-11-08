<script setup>
import {
  ageAt,
  childBirthFromIin,
  selectChildCount,
} from "../model/children.js";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { isDemo } from "@/shared/config";
import { reactive, computed, watch, onMounted, useId } from "vue";
import { Modal } from "@/shared/ui";
import {
  useBookingStore,
  dateAfter,
  nightsBetween,
  quoteStay,
  validateChildren,
  paymentTerms,
  customerQuote,
} from "@/entities/booking";
import { ref } from "vue";
import { useGuestAccountStore } from "@/entities/guest-account";
const guestAccount = useGuestAccountStore();
import { money } from "@/shared/lib";
const props = defineProps({
  resort: Object,
  rooms: Array,
  tariffs: Array,
  preset: Object,
  staff: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  roomId: props.rooms.find((r) => r.status === "active")?.id || "",
  ...(props.staff
    ? {}
    : { tariffId: props.tariffs.find((t) => t.status === "active")?.id || "" }),
  start: dateAfter(7),
  end: dateAfter(10),
  guests: 2,
  childrenAges: [],
  guestLabel: "",
  guestPhone: "",
  ...props.preset,
});
const room = computed(() => props.rooms.find((r) => r.id === form.roomId));
const tariff = computed(() =>
  props.tariffs.find((t) => t.id === form.tariffId),
);
const price = computed(() =>
  room.value &&
  (props.staff || tariff.value) &&
  !validateChildren(form.guests, form.childrenAges)
    ? quoteStay(room.value, props.staff ? null : tariff.value, form)
    : null,
);
const total = computed(() => price.value?.total || 0);
const settlement = computed(() =>
  price.value ? paymentTerms(props.resort, total.value) : null,
);
const displayPrice = computed(() => customerQuote(props.resort, price.value));
const quotedTariffs = computed(() =>
  props.tariffs
    .filter((offer) => offer.status === "active")
    .map((offer) => ({
      ...offer,
      quote: room.value
        ? customerQuote(props.resort, quoteStay(room.value, offer, form))
        : null,
    })),
);
const children = ref([]);
watch(
  [children, () => form.start],
  () => {
    form.childrenAges = children.value.map((c) =>
      ageAt(childBirthFromIin(c.iin, form.start, dateAfter()), form.start),
    );
  },
  { deep: true },
);
onMounted(async () => {
  if (!props.staff) {
    try {
      await guestAccount.restore();
    } catch (e) {
      error.value = e.message;
    }
  }
});
const childCountId = useId();
const childCountInput = ref("0");
const maxChildren = computed(() =>
  Math.max(0, (room.value?.capacity || 4) - 1),
);
function setChildCount(value) {
  childCountInput.value = String(value);
  const next = selectChildCount(value, form.guests, room.value?.capacity || 4);
  if (!next) return;
  children.value = Array.from(
    { length: next.children },
    (_, i) => children.value[i] ?? { iin: "" },
  );
  childCountInput.value = String(next.children);
  form.guests = next.guests;
}
function commitChildCount() {
  setChildCount(childCountInput.value === "" ? 0 : childCountInput.value);
  childCountInput.value = String(children.value.length);
}
watch(
  () => form.guests,
  (value) => {
    if (value === "" || !Number.isInteger(Number(value)) || Number(value) < 1)
      return;
    const count = Math.min(children.value.length, Number(value) - 1);
    if (count !== children.value.length) {
      children.value = children.value.slice(0, count);
      childCountInput.value = String(count);
    }
  },
);
const store = useBookingStore(),
  busy = ref(false),
  error = ref(""),
  consent = ref(false);
let attempt = null;
async function save() {
  error.value =
    !props.staff && !guestAccount.authenticated
      ? t("common.checkout.loginRequired")
      : children.value.some(
            (c) => !childBirthFromIin(c.iin, form.start, dateAfter()),
          )
        ? t("common.children.invalidIin")
        : validateChildren(form.guests, form.childrenAges);
  if (error.value) return;
  if (price.value && !settlement.value) {
    error.value = t("common.settlement.notConfigured");
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const fingerprint = JSON.stringify(form);
    if (attempt?.fingerprint !== fingerprint)
      attempt = { fingerprint, id: crypto.randomUUID() };
    const { guestLabel, guestPhone, ...publicForm } = form;
    const result = await store.create(
      {
        ...(props.staff ? form : publicForm),
        childrenBirthDates: children.value.map((c) =>
          childBirthFromIin(c.iin, form.start, dateAfter()),
        ),
        requestId: attempt.id,
      },
      props.staff,
    );
    emit("saved", result);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
watch(
  () => form.roomId,
  () => {
    if (room.value && form.guests > room.value.capacity)
      form.guests = room.value.capacity;
  },
);
</script>
<template>
  <Modal
    :title="
      staff
        ? t('public.addBooking')
        : t('public.yourStayAt') + ' ' + resort.name
    "
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save">
      <div class="booking-property">
        <img
          :src="
            room?.media?.find((m) => m.kind === 'image')?.url ||
            '/assets/room.jpg'
          "
          :alt="
            room?.media?.find((m) => m.kind === 'image')?.alt ||
            t('public.illustrativeRoomImage')
          "
        />
        <div>
          <h3>{{ resort.name }}</h3>
          <p>{{ resort.city }}</p>
        </div>
      </div>
      <label v-if="staff"
        >{{ t("public.guestName")
        }}<input
          v-model="form.guestLabel"
          required
          maxlength="80"
          :placeholder="t('public.forExampleDemoGuest01')"
      /></label>
      <label v-if="staff && !isDemo"
        >{{ t("public.contactPhone")
        }}<input
          v-model="form.guestPhone"
          type="tel"
          :required="!staff"
          maxlength="30"
          placeholder="+7 …"
      /></label>
      <p v-if="staff && isDemo" class="field-help">
        {{ t("public.useFictionalDetailsForTesting") }}
      </p>
      <p v-if="!staff" class="field-help">
        {{
          t("common.checkout.profileContact", {
            name: guestAccount.session?.profile?.name || "—",
            phone: guestAccount.session?.account?.phone || "—",
          })
        }}
      </p>
      <RouterLink
        v-if="!staff && !guestAccount.authenticated"
        to="/account/login"
        class="field-help"
        >{{ t("common.checkout.loginRequired") }}</RouterLink
      >
      <div class="form-grid">
        <label
          >{{ t("public.checkin")
          }}<input
            v-model="form.start"
            type="date"
            :min="dateAfter()"
            required /></label
        ><label
          >{{ t("public.checkout")
          }}<input
            v-model="form.end"
            type="date"
            :min="form.start"
            required /></label
        ><label
          >{{ t("public.roomInReceiptPage")
          }}<select v-model="form.roomId" required>
            <option disabled value="">{{ t("public.noActiveRooms") }}</option>
            <option
              v-for="r in rooms.filter((r) => r.status === 'active')"
              :key="r.id"
              :value="r.id"
            >
              № {{ r.number }} · {{ r.title }}
            </option>
          </select></label
        ><label
          >{{ t("public.guests")
          }}<input
            v-model.number="form.guests"
            type="number"
            min="1"
            :max="room?.capacity || 4"
            required
        /></label>
      </div>
      <fieldset class="pricing-fields">
        <legend>{{ t("common.pricing.children") }}</legend>
        <div class="child-count-field">
          <label :for="childCountId">{{
            t("common.pricing.childCount")
          }}</label>
          <div class="child-count-control">
            <button
              type="button"
              class="secondary"
              :aria-label="t('common.children.remove')"
              :disabled="children.length === 0"
              @click="setChildCount(children.length - 1)"
            >
              −
            </button>
            <input
              :id="childCountId"
              :value="childCountInput"
              type="number"
              inputmode="numeric"
              min="0"
              :max="maxChildren"
              step="1"
              :aria-describedby="`${childCountId}-help`"
              required
              @input="setChildCount($event.target.value)"
              @blur="commitChildCount"
            />
            <button
              type="button"
              class="secondary"
              :aria-label="t('common.children.add')"
              :disabled="children.length >= maxChildren"
              @click="setChildCount(children.length + 1)"
            >
              +
            </button>
          </div>
          <p :id="`${childCountId}-help`" class="field-help">
            {{ t("common.children.partySizeHint") }}
          </p>
        </div>
        <div
          v-for="(child, index) in children"
          :key="index"
          class="child-birth-fields"
        >
          <label
            >{{ t("common.children.iin", { number: index + 1 })
            }}<input
              v-model="child.iin"
              inputmode="numeric"
              minlength="12"
              maxlength="12"
              pattern="[0-9]{12}"
              autocomplete="off"
              required
          /></label>
          <p class="field-help">
            {{
              t("common.children.age", { age: form.childrenAges[index] ?? "—" })
            }}
          </p>
        </div>
        <p v-if="children.length" class="field-help">
          {{ t("common.children.hint") }}
        </p>
      </fieldset>
      <label v-if="!staff"
        >{{ t("public.rate")
        }}<select v-model="form.tariffId" required>
          <option disabled value="">{{ t("public.noActiveRates") }}</option>
          <option
            v-for="offer in quotedTariffs"
            :key="offer.id"
            :value="offer.id"
          >
            {{ offer.name
            }}{{
              offer.priceKind === "discount"
                ? t("public.discountInBookingEditor", [offer.discountPercent])
                : ""
            }}
            {{
              offer.quote
                ? " · " +
                  t("common.pricing.selectedStayTotal", {
                    nights: offer.quote.nights,
                    total: money(offer.quote.total),
                  })
                : ""
            }}
          </option>
        </select></label
      >
      <div class="quote">
        <div>
          <span
            >{{ t("public.totalFor") }}
            {{ Math.max(0, nightsBetween(form.start, form.end)) || 0 }}
            {{ t("public.nightsInBookingEditor") }}</span
          ><small
            >{{
              t(staff ? "staff.board.roomPriceFor" : "public.roomAndRateFor")
            }}
            {{ form.guests }} {{ t("public.guestsInBookingEditor") }}</small
          >
        </div>
        <strong>{{ displayPrice ? money(displayPrice.total) : "—" }}</strong>
      </div>
      <dl v-if="settlement" class="booking-settlement">
        <div>
          <dt>{{ t("common.settlement.online") }}</dt>
          <dd>{{ money(settlement.onlineAmount) }}</dd>
        </div>
        <div>
          <dt>{{ t("common.settlement.onsite") }}</dt>
          <dd>{{ money(settlement.onsiteAmount) }}</dd>
        </div>
      </dl>
      <p v-else-if="price" class="form-error" role="status">
        {{ t("common.settlement.notConfigured") }}
      </p>
      <p v-if="tariff?.childrenUnderThreeFree" class="field-help">
        {{ t("common.pricing.freeUnderThree") }}
      </p>
      <details v-if="displayPrice" class="price-breakdown">
        <summary>{{ t("common.pricing.breakdown") }}</summary>
        <dl>
          <div v-for="line in displayPrice.nightlyBreakdown" :key="line.date">
            <dt>
              {{ line.date }} <small>{{ line.periodLabel }}</small>
            </dt>
            <dd>{{ money(line.nightly) }}</dd>
          </div>
        </dl>
        <p class="field-help">{{ t("common.pricing.preview") }}</p>
      </details>
      <p class="field-help">
        {{ t("public.checkinFrom") }} {{ resort.checkInTime || "14:00" }} ·
        {{ resort.timeZone || "Asia/Almaty"
        }}{{ t("public.refunds100At48HoursOrMore70At2448HoursNone") }}
      </p>
      <label class="consent"
        ><input v-model="consent" type="checkbox" required />
        {{
          isDemo
            ? t("public.thisIsADemoBookingWithNoRealCharge")
            : t(
                "public.sendTheRequestToTheManagerTheBookingRequiresConfirmationNothingIs",
              )
        }}</label
      >
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("public.cancel") }}</button
        ><button
          class="primary"
          :disabled="
            busy ||
            !price ||
            !settlement ||
            (!staff && !guestAccount.authenticated)
          "
        >
          {{
            busy
              ? t("public.saving")
              : isDemo
                ? t("public.createDemoRequest")
                : t("public.sendRequest")
          }}
        </button>
      </div>
    </form></Modal
  >
</template>
<style scoped>
.child-count-field {
  min-width: 0;
}
.child-count-control {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
}
.child-count-control button {
  flex: 0 0 3rem;
  min-width: 3rem;
  min-height: 3rem;
  padding: 0;
  font-size: 1.5rem;
}
.child-count-control input {
  width: 100%;
  min-width: 0;
  max-width: 8rem;
  text-align: center;
}
.child-count-field .field-help {
  margin-bottom: 0;
}
.booking-settlement {
  margin: 0;
  padding: 0.875rem 1rem;
  border: 1px solid #dbe3d8;
  border-radius: 14px;
}
.booking-settlement > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.25rem 0;
}
.booking-settlement dt {
  color: #617067;
}
.booking-settlement dd {
  margin: 0;
  font-weight: 700;
  white-space: nowrap;
}
</style>
