<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { PublicHeader } from "@/widgets/public-header";
import { MediaGallery } from "@/widgets/media-gallery";
import { BookingEditor } from "@/features/create-booking";
import {
  dateAfter,
  validateSearch,
  nightsBetween,
  quoteStay,
} from "@/entities/booking";
import { request } from "@/shared/api";
import { money, categoryNames } from "@/shared/lib";
const route = useRoute();
const router = useRouter();
const data = ref(null),
  loading = ref(true),
  error = ref(""),
  searching = ref(false),
  searchError = ref(""),
  available = ref(null),
  checkout = ref(false),
  success = ref(null),
  tariffId = ref("");
const dates = reactive({
  start: String(route.query.start || dateAfter(7)),
  end: String(route.query.end || dateAfter(10)),
  guests: Number(route.query.guests) || 2,
});
const room = computed(() => data.value?.room),
  resort = computed(() => data.value?.resort),
  tariffs = computed(() =>
    (data.value?.tariffs || []).filter((t) => t.status === "active"),
  ),
  tariff = computed(() => tariffs.value.find((t) => t.id === tariffId.value));
const price = computed(() =>
  room.value && tariff.value
    ? quoteStay(room.value, tariff.value, dates)
    : null,
);
const nightly = computed(() => price.value?.nightly);
const originalNight = computed(() => price.value?.regularNightly);
const nights = computed(
  () => Math.max(0, nightsBetween(dates.start, dates.end)) || 0,
);
let generation = 0,
  searchGeneration = 0;
async function load() {
  const run = ++generation;
  searchGeneration++;
  loading.value = true;
  error.value = "";
  data.value = null;
  available.value = null;
  success.value = null;
  try {
    const result = await request(
      "GET",
      `/rooms/${encodeURIComponent(route.params.id)}`,
    );
    if (run !== generation) return;
    data.value = result;
    tariffId.value =
      result.tariffs.find((t) => t.status === "active")?.id || "";
    if (dates.guests > result.room.capacity)
      dates.guests = result.room.capacity;
  } catch (e) {
    if (run === generation)
      error.value =
        e.status === 404
          ? t("public.thisRoomWasNotFoundOrIsNoLongerAvailableToBook")
          : e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
  if (run === generation && data.value && route.query.start) await checkDates();
}
async function checkDates() {
  searchError.value = validateSearch(dates);
  if (searchError.value) return;
  const run = ++searchGeneration;
  searching.value = true;
  try {
    const result = await request(
      "GET",
      "/availability?" + new URLSearchParams(dates),
    );
    if (run === searchGeneration)
      available.value = result.roomIds.includes(room.value.id);
  } catch (e) {
    if (run === searchGeneration) searchError.value = e.message;
  } finally {
    if (run === searchGeneration) searching.value = false;
  }
}
async function saved(booking) {
  checkout.value = false;
  success.value = booking;
  available.value = false;
  await router.push({ path: "/bookings", query: { pay: booking.id } });
}
watch(dates, () => {
  searchGeneration++;
  available.value = null;
  searching.value = false;
  searchError.value = "";
});
watch(() => route.params.id, load, { immediate: true });
</script>
<template>
  <div class="public-site room-profile-page">
    <PublicHeader />
    <main id="public-main" class="profile-main">
      <RouterLink
        class="profile-back"
        :to="resort ? `/resorts/${resort.id}` : '/'"
        >←
        {{
          resort?.name || t("public.allResortsInRoomProfilePage")
        }}</RouterLink
      >
      <div v-if="loading" class="profile-feedback" role="status">
        {{ t("public.loadingRoom") }}
      </div>
      <div v-else-if="error" class="profile-feedback" role="alert">
        <h1>{{ t("public.unableToOpenRoom") }}</h1>
        <p>{{ error }}</p>
        <button class="secondary" @click="load">{{ t("public.retry") }}</button>
      </div>
      <template v-else-if="room && resort">
        <header class="profile-heading">
          <div>
            <span class="eyebrow"
              >{{ resort.name }} · {{ categoryNames[room.category] }} · №
              {{ room.number }}</span
            >
            <h1>{{ room.title }}</h1>
            <p>
              {{ t("public.upTo") }} {{ room.capacity }}
              {{ t("public.guestsInResortProfilePage") }} {{ room.area }}
              {{ t("public.m") }} {{ room.beds }}
            </p>
          </div>
          <span class="profile-class">{{ categoryNames[room.category] }}</span>
        </header>
        <MediaGallery
          :media="room.media || []"
          :title="room.title"
          fallback="/assets/room.jpg"
        />
        <div v-if="success" class="booking-success" role="status">
          <span class="success-icon">✓</span>
          <div>
            <h2>{{ t("public.requestSent") }}</h2>
            <p>
              {{ t("public.managerConfirmation", { resort: resort.name }) }}
            </p>
            <RouterLink class="primary button-link" to="/bookings">{{
              t("public.openMyBookings")
            }}</RouterLink>
          </div>
        </div>
        <div class="profile-columns">
          <div class="profile-content">
            <section class="profile-section">
              <h2>{{ t("public.aboutThisRoom") }}</h2>
              <p class="profile-description">
                {{
                  room.description ||
                  t(
                    "public.aRoomDescriptionWillBeAddedSoonKeyDetailsAndAvailableRates",
                  )
                }}
              </p>
              <ul v-if="room.amenities?.length" class="amenity-tags">
                <li v-for="amenity in room.amenities" :key="amenity">
                  ✓ {{ amenity }}
                </li>
              </ul>
              <dl class="checkin-facts">
                <div>
                  <dt>{{ t("public.checkin") }}</dt>
                  <dd>
                    {{ resort.checkInTime || "14:00" }}
                  </dd>
                </div>
                <div v-if="resort.checkOutTime">
                  <dt>{{ t("public.checkout") }}</dt>
                  <dd>{{ resort.checkOutTime }}</dd>
                </div>
                <div>
                  <dt>{{ t("public.localTime") }}</dt>
                  <dd>{{ resort.timeZone || "Asia/Almaty" }}</dd>
                </div>
              </dl>
            </section>
            <section class="profile-section">
              <h2>{{ t("public.chooseARate") }}</h2>
              <p class="field-help">
                {{
                  t("public.thePriceIsPerRoomPerNightForYourSelectedGuestCount")
                }}
              </p>
              <div v-if="!tariffs.length" class="profile-feedback">
                {{
                  t("public.noRatesAreAvailableForThisRoomYetReturnToTheResort")
                }}
              </div>
              <div
                class="profile-tariffs"
                role="radiogroup"
                :aria-label="t('public.roomRates')"
              >
                <label
                  v-for="offer in tariffs"
                  :key="offer.id"
                  :class="[
                    'profile-tariff',
                    { selected: tariffId === offer.id },
                  ]"
                  ><input
                    v-model="tariffId"
                    type="radio"
                    name="room-tariff"
                    :value="offer.id"
                  />
                  <div>
                    <div class="section-title-row">
                      <h3>{{ offer.name }}</h3>
                      <span
                        v-if="
                          offer.priceKind === 'discount' &&
                          offer.discountPercent
                        "
                        :class="[
                          'price-kind',
                          { discount: offer.priceKind === 'discount' },
                        ]"
                        >{{
                          t("public.discount", [offer.discountPercent])
                        }}</span
                      >
                    </div>
                    <p>{{ offer.description }}</p>
                    <ul>
                      <li v-for="feature in offer.features" :key="feature">
                        {{ feature }}
                      </li>
                    </ul>
                    <div class="tariff-price">
                      <del v-if="offer.discountPercent">{{
                        money(room.price + offer.supplement * dates.guests)
                      }}</del
                      ><strong>{{
                        money(
                          Math.round(
                            ((room.price + offer.supplement * dates.guests) *
                              (100 - (offer.discountPercent || 0))) /
                              100,
                          ),
                        )
                      }}</strong
                      ><small> {{ t("public.night") }}</small>
                    </div>
                  </div></label
                >
              </div>
            </section>
            <section class="profile-section">
              <h2>{{ t("public.cancellationAndRefunds") }}</h2>
              <p class="profile-description">
                {{ t("public.theDeadlineIsCalculatedBeforeCheckin") }}
                {{ resort.checkInTime || "14:00" }},
                {{ resort.timeZone || "Asia/Almaty"
                }}{{ t("public.theseTermsAreSavedWhenYouBook") }}
              </p>
              <div class="refund-steps">
                <div>
                  <strong>100%</strong
                  ><span>{{ t("public.48HoursOrMore") }}</span>
                </div>
                <div>
                  <strong>70%</strong><span>{{ t("public.24To48Hours") }}</span>
                </div>
                <div>
                  <strong>0%</strong
                  ><span>{{ t("public.lessThan24Hours") }}</span>
                </div>
              </div>
              <p class="field-help">
                {{
                  t(
                    "public.kaspiDemoSimulatesPaymentsAndRefundsNoRealMoneyIsCharged",
                  )
                }}
              </p>
            </section>
          </div>
          <aside class="profile-aside">
            <form class="stay-summary" @submit.prevent="checkDates">
              <span class="eyebrow">{{ t("public.yourStay") }}</span>
              <h2>
                {{
                  nightly == null ? t("common.pricing.varies") : money(nightly)
                }}<small> {{ t("public.night") }}</small>
              </h2>
              <del
                v-if="tariff?.discountPercent && originalNight != null"
                class="muted"
                >{{ money(originalNight) }}</del
              >
              <p class="field-help">
                {{ t("common.pricing.childrenAtCheckout") }}
              </p>
              <div class="stay-date-form compact">
                <label
                  >{{ t("public.checkin")
                  }}<input
                    v-model="dates.start"
                    type="date"
                    :min="dateAfter()"
                    required /></label
                ><label
                  >{{ t("public.checkout")
                  }}<input
                    v-model="dates.end"
                    type="date"
                    :min="dates.start"
                    required /></label
                ><label
                  >{{ t("public.guests")
                  }}<input
                    v-model.number="dates.guests"
                    type="number"
                    min="1"
                    :max="room.capacity"
                    required
                /></label>
              </div>
              <p class="small muted">
                {{ t("public.checkinFrom") }}
                {{ resort.checkInTime || "14:00" }} ·
                {{ resort.timeZone || "Asia/Almaty" }}
              </p>
              <p v-if="searchError" class="form-error" role="alert">
                {{ searchError }}
              </p>
              <p
                v-if="available === false"
                class="availability-note unavailable"
                role="status"
              >
                {{
                  t("public.thisRoomIsBookedForTheseDatesChooseDifferentDates")
                }}
              </p>
              <p
                v-if="available === true"
                class="availability-note"
                role="status"
              >
                {{ t("public.thisRoomIsAvailableForYourDates") }}
              </p>
              <button
                v-if="available !== true"
                class="primary full-width"
                :disabled="searching || !tariff"
              >
                {{
                  searching
                    ? t("public.checking")
                    : t("public.checkAvailability")
                }}</button
              ><template v-else
                ><div class="stay-total">
                  <span
                    >{{ nights }} {{ t("public.nights") }}
                    {{
                      nightly == null
                        ? t("common.pricing.varies")
                        : money(nightly)
                    }}</span
                  ><strong>{{ price ? money(price.total) : "—" }}</strong>
                </div>
                <button
                  type="button"
                  class="primary full-width"
                  :disabled="!tariff"
                  @click="checkout = true"
                >
                  {{ t("public.sendRequest") }}
                </button></template
              >
              <p class="field-help">
                {{
                  t(
                    "public.managerConfirmationComesFirstThenPaymentOnlySimulatedPaymentsAreAvailableNow",
                  )
                }}
              </p>
            </form>
          </aside>
        </div>
      </template>
      <BookingEditor
        v-if="checkout && room && resort"
        :resort="resort"
        :rooms="[room]"
        :tariffs="tariffs"
        :preset="{ ...dates, roomId: room.id, tariffId }"
        @close="checkout = false"
        @saved="saved"
      />
    </main>
  </div>
</template>
