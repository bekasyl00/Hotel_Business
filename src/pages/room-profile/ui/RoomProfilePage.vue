<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { computed, nextTick, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { PublicHeader } from "@/widgets/public-header";
import { MediaGallery } from "@/widgets/media-gallery";
import { AvailabilityCalendar } from "@/widgets/availability-calendar";
import { BookingEditor } from "@/features/create-booking";
import {
  dateAfter,
  validateSearch,
  nightsBetween,
  quoteStay,
  paymentTerms,
  customerQuote,
  customerNightPrice,
  CustomerNightPrice,
} from "@/entities/booking";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
import { useGuestAccountStore } from "@/entities/guest-account";
const guestAccount = useGuestAccountStore();
import { money, categoryNames, whatsAppUrl, twoGisUrl } from "@/shared/lib";
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
const quotedTariffs = computed(() =>
  tariffs.value.map((offer) => {
    const quote = room.value ? quoteStay(room.value, offer, dates) : null;
    return {
      ...offer,
      quote: customerQuote(resort.value, quote),
      arrivalPrice: customerNightPrice(resort.value, room.value, offer, dates),
    };
  }),
);
const settlement = computed(() =>
  price.value ? paymentTerms(resort.value, price.value.total) : null,
);
const displayPrice = computed(() => customerQuote(resort.value, price.value));
const arrivalPrice = computed(() =>
  customerNightPrice(resort.value, room.value, tariff.value, dates),
);
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
      result.tariffs.find(
        (t) => t.id === route.query.tariffId && t.status === "active",
      )?.id ||
      result.tariffs.find((t) => t.status === "active")?.id ||
      "";
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
  if (run === generation && available.value && route.query.checkout === "1") {
    const { checkout: _checkout, ...query } = route.query;
    await router.replace({ query });
    await openCheckout();
  }
}
async function selectCalendarDates(range) {
  Object.assign(dates, range);
  await nextTick();
  await checkDates();
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
async function openCheckout() {
  searchError.value = "";
  try {
    await guestAccount.restore();
    if (!guestAccount.authenticated) {
      const next = router.resolve({
        path: route.path,
        query: { ...dates, tariffId: tariffId.value, checkout: "1" },
      }).href;
      await router.push({ path: "/account/login", query: { next } });
      return;
    }
    checkout.value = true;
  } catch (e) {
    searchError.value = e.message;
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
        <section class="profile-section profile-introduction">
          <h2>{{ t("public.aboutThisRoom") }}</h2>
          <p class="profile-description">
            {{
              room.description ||
              t(
                "public.aRoomDescriptionWillBeAddedSoonKeyDetailsAndAvailableRates",
              )
            }}
          </p>
        </section>
        <MediaGallery
          :media="room.media || []"
          :title="room.title"
          fallback="/assets/room.jpg"
        />
        <section
          v-if="room.descriptionAfter"
          class="profile-section profile-introduction"
        >
          <h2>{{ t("common.catalogContent.moreAboutStay") }}</h2>
          <p class="profile-description">{{ room.descriptionAfter }}</p>
        </section>
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
              <ul v-if="room.amenities?.length" class="amenity-tags">
                <li v-for="amenity in room.amenities" :key="amenity">
                  ✓ {{ amenity }}
                </li>
              </ul>
              <div
                class="profile-contact-links"
                v-if="
                  whatsAppUrl(resort.staffWhatsApp) ||
                  twoGisUrl(resort.twoGisUrl)
                "
              >
                <a
                  v-if="whatsAppUrl(resort.staffWhatsApp)"
                  :href="whatsAppUrl(resort.staffWhatsApp)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="secondary button-link"
                  >{{ t("common.catalogContent.contactStaff") }}</a
                >
                <a
                  v-if="twoGisUrl(resort.twoGisUrl)"
                  :href="twoGisUrl(resort.twoGisUrl)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="secondary button-link"
                  >{{ t("common.catalogContent.openTwoGis") }}</a
                >
              </div>
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
            <AvailabilityCalendar
              :resort-id="resort.id"
              :category="room.category"
              :room-id="room.id"
              :guests="dates.guests"
              :time-zone="resort.timeZone"
              :start="dates.start"
              :end="dates.end"
              @select="selectCalendarDates"
            />
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
                  v-for="offer in quotedTariffs"
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
                    </div>
                    <p>{{ offer.description }}</p>
                    <ul>
                      <li v-for="feature in offer.features" :key="feature">
                        {{ feature }}
                      </li>
                    </ul>
                    <CustomerNightPrice :price="offer.arrivalPrice" />
                    <p v-if="offer.quote" class="field-help">
                      {{
                        t("common.pricing.selectedStayTotal", {
                          nights: offer.quote.nights,
                          total: money(offer.quote.total),
                        })
                      }}
                    </p>
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
              <p v-if="isDemo" class="field-help">
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
              <CustomerNightPrice :price="arrivalPrice" prominent />
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
                    >{{ t("common.settlement.total") }} · {{ nights }}
                    {{ t("public.nightsInBookingEditor") }}</span
                  >
                  <strong>{{
                    displayPrice ? money(displayPrice.total) : "—"
                  }}</strong>
                </div>
                <dl v-if="settlement" class="stay-settlement">
                  <div>
                    <dt>{{ t("common.settlement.online") }}</dt>
                    <dd>{{ money(settlement.onlineAmount) }}</dd>
                  </div>
                  <div>
                    <dt>{{ t("common.settlement.onsite") }}</dt>
                    <dd>{{ money(settlement.onsiteAmount) }}</dd>
                  </div>
                </dl>
                <button
                  type="button"
                  class="primary full-width"
                  :disabled="!tariff"
                  @click="openCheckout"
                >
                  {{ t("public.sendRequest") }}
                </button></template
              >
              <p v-if="isDemo" class="field-help">
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
<style scoped>
.stay-settlement {
  margin: 0 0 1rem;
  font-size: 0.85rem;
}
.stay-settlement > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0.5rem 0;
}
.stay-settlement dt {
  color: #617067;
}
.stay-settlement dd {
  margin: 0;
  font-weight: 700;
  white-space: nowrap;
}
</style>
