<script setup>
import { ageAt, childBirthFromIin } from "../model/children.js";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { isDemo } from "@/shared/config";
import { reactive, computed, watch, onMounted } from "vue";
import { Modal } from "@/shared/ui";
import {
  useBookingStore,
  dateAfter,
  nightsBetween,
  quoteStay,
  validateChildren,
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
const childCount = computed({
  get: () => children.value.length,
  set: (value) => {
    children.value = Array.from(
      { length: Math.max(0, Math.min(Number(value) || 0, form.guests - 1)) },
      (_, i) => children.value[i] ?? { iin: "" },
    );
  },
});
watch(
  () => form.guests,
  (value) => {
    children.value = children.value.slice(0, Math.max(0, value - 1));
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
        <label
          >{{ t("common.pricing.childCount")
          }}<input
            v-model.number="childCount"
            type="number"
            min="0"
            :max="Math.max(0, form.guests - 1)"
            required
        /></label>
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
            v-for="offer in tariffs.filter(
              (offer) => offer.status === 'active',
            )"
            :key="offer.id"
            :value="offer.id"
          >
            {{ offer.name
            }}{{
              offer.priceKind === "discount"
                ? t("public.discountInBookingEditor", [offer.discountPercent])
                : ""
            }}
            · +{{ money(offer.supplement) }} {{ t("public.guestNight") }}
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
        <strong>{{ price ? money(total) : "—" }}</strong>
      </div>
      <p v-if="tariff?.childrenUnderThreeFree" class="field-help">
        {{ t("common.pricing.freeUnderThree") }}
      </p>
      <details v-if="price" class="price-breakdown">
        <summary>{{ t("common.pricing.breakdown") }}</summary>
        <dl>
          <div v-for="line in price.nightlyBreakdown" :key="line.date">
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
          :disabled="busy || !price || (!staff && !guestAccount.authenticated)"
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
