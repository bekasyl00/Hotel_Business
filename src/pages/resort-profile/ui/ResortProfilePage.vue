<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { computed, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { PublicHeader } from "@/widgets/public-header";
import { MediaGallery } from "@/widgets/media-gallery";
import { dateAfter, validateSearch, nightsBetween } from "@/entities/booking";
import { GeoMap } from "@/shared/ui";
import { request } from "@/shared/api";
import { money, dateLabel, categoryNames } from "@/shared/lib";
const route = useRoute();
const data = ref(null),
  loading = ref(true),
  error = ref(""),
  searching = ref(false),
  searchError = ref(""),
  available = ref(null),
  roomClass = ref("all");
const dates = reactive({
  start: String(route.query.start || dateAfter(7)),
  end: String(route.query.end || dateAfter(10)),
  guests: Number(route.query.guests) || 2,
});
const resort = computed(() => data.value?.resort);
const rooms = computed(() =>
  (data.value?.rooms || []).filter(
    (room) =>
      room.status === "active" &&
      (roomClass.value === "all" || room.category === roomClass.value) &&
      (available.value === null || available.value.includes(room.id)),
  ),
);
const reviews = computed(() => data.value?.reviews || []);
const rating = computed(() =>
  reviews.value.length
    ? (
        reviews.value.reduce((sum, r) => sum + Number(r.rating), 0) /
        reviews.value.length
      ).toFixed(1)
    : null,
);
const point = computed(() =>
  resort.value ? [{ ...resort.value, label: resort.value.name }] : [],
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
  try {
    const result = await request(
      "GET",
      `/resorts/${encodeURIComponent(route.params.id)}`,
    );
    if (run === generation) data.value = result;
  } catch (e) {
    if (run === generation)
      error.value =
        e.status === 404
          ? t("public.thisResortWasNotFoundOrIsNoLongerPublished")
          : e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
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
    if (run === searchGeneration) available.value = result.roomIds;
  } catch (e) {
    if (run === searchGeneration) searchError.value = e.message;
  } finally {
    if (run === searchGeneration) searching.value = false;
  }
}
const roomLink = (room) => ({
  path: `/rooms/${room.id}`,
  query: available.value === null ? {} : { ...dates },
});
watch(dates, () => {
  searchGeneration++;
  available.value = null;
  searching.value = false;
  searchError.value = "";
});
watch(() => route.params.id, load, { immediate: true });
</script>
<template>
  <div class="public-site">
    <PublicHeader />
    <main id="public-main" class="profile-main">
      <RouterLink class="profile-back" to="/">{{
        t("public.allResorts")
      }}</RouterLink>
      <div v-if="loading" class="profile-feedback" role="status">
        {{ t("public.loadingResort") }}
      </div>
      <div v-else-if="error" class="profile-feedback" role="alert">
        <h1>{{ t("public.unableToOpenResort") }}</h1>
        <p>{{ error }}</p>
        <button class="secondary" @click="load">{{ t("public.retry") }}</button>
      </div>
      <template v-else-if="resort">
        <header class="profile-heading">
          <div>
            <div class="profile-chips">
              <span>{{
                {
                  wellness: t("public.wellness"),
                  family: t("public.forFamilies"),
                  premium: t("public.premium"),
                  nature: t("public.inNature"),
                }[resort.category] || t("public.resort")
              }}</span
              ><span
                >{{ t("public.class") }}
                {{
                  {
                    standard: t("public.standard"),
                    comfort: t("public.comfort"),
                    premium: t("public.premium"),
                  }[resort.resortClass] || t("public.standard")
                }}</span
              >
            </div>
            <h1>{{ resort.name }}</h1>
            <p>{{ resort.city }} · {{ resort.address }}</p>
          </div>
          <a v-if="rating" class="profile-rating" href="#reviews"
            ><strong>★ {{ rating }}</strong
            ><span>{{ t("public.reviews") }} {{ reviews.length }}</span></a
          ><a v-else class="small" href="#reviews">{{
            t("public.noReviewsYet")
          }}</a>
        </header>
        <MediaGallery :media="resort.media || []" :title="resort.name" />
        <nav
          class="profile-section-nav"
          :aria-label="t('public.resortPageSections')"
        >
          <a href="#about">{{ t("public.aboutTheResort") }}</a
          ><a href="#rooms">{{ t("public.roomsAndDates") }}</a
          ><a href="#reviews">{{ t("public.reviewsInResortProfilePage") }}</a
          ><a href="#location">{{ t("public.onTheMapInResortProfilePage") }}</a>
        </nav>
        <div class="profile-columns">
          <div class="profile-content">
            <section id="about" class="profile-section">
              <span class="eyebrow">{{ t("public.aPlaceForYourBreak") }}</span>
              <h2>{{ t("public.aboutTheResort") }}</h2>
              <p class="profile-description">
                {{
                  resort.description ||
                  t("public.aResortDescriptionWillBeAddedSoon")
                }}
              </p>
              <ul v-if="resort.amenities?.length" class="amenity-tags">
                <li v-for="item in resort.amenities" :key="item">
                  ✓ {{ item }}
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
            <section id="rooms" class="profile-section">
              <div class="section-title-row">
                <div>
                  <span class="eyebrow">{{ t("public.aRoomForYou") }}</span>
                  <h2>{{ t("public.chooseDatesAndARoom") }}</h2>
                </div>
                <label
                  ><span class="sr-only">{{ t("public.roomCategory") }}</span
                  ><select v-model="roomClass">
                    <option value="all">{{ t("public.allRooms") }}</option>
                    <option value="standard">{{ t("public.standard") }}</option>
                    <option value="comfort">{{ t("public.comfort") }}</option>
                    <option value="suite">{{ t("public.suite") }}</option>
                  </select></label
                >
              </div>
              <form class="stay-date-form" @submit.prevent="checkDates">
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
                    max="4"
                    required /></label
                ><button class="primary" :disabled="searching">
                  {{ searching ? t("public.checking") : t("public.findRooms") }}
                </button>
              </form>
              <p v-if="searchError" class="form-error" role="alert">
                {{ searchError }}
              </p>
              <p class="field-help" role="status">
                {{
                  available === null
                    ? t("public.chooseDatesToCheckAvailableRooms")
                    : t("public.availableForYourDatesNights", [
                        rooms.length,
                        nightsBetween(dates.start, dates.end),
                      ])
                }}
              </p>
              <div v-if="!rooms.length" class="profile-feedback">
                <h3>
                  {{
                    available === null
                      ? t("public.roomsAreNotPublishedYet")
                      : t("public.noRoomsAvailableForTheseDates")
                  }}
                </h3>
                <p>
                  {{
                    available === null
                      ? t("public.returnToTheCatalogueToChooseAnotherResort")
                      : t("public.changeTheDatesGuestCountOrCategory")
                  }}
                </p>
              </div>
              <article
                v-for="room in rooms"
                :key="room.id"
                class="profile-room-card"
              >
                <RouterLink :to="roomLink(room)"
                  ><img
                    :src="
                      room.media?.find((m) => m.kind === 'image')?.url ||
                      '/assets/room.jpg'
                    "
                    :alt="
                      room.media?.length
                        ? room.title
                        : t('public.illustrativeRoomImage')
                    "
                    loading="lazy"
                /></RouterLink>
                <div>
                  <span class="eyebrow"
                    >{{ categoryNames[room.category] }} · №
                    {{ room.number }}</span
                  ><RouterLink :to="roomLink(room)"
                    ><h3>{{ room.title }}</h3></RouterLink
                  >
                  <p class="small muted">
                    {{ t("public.upTo") }} {{ room.capacity }}
                    {{ t("public.guestsInResortProfilePage") }} {{ room.area }}
                    {{ t("public.m") }} {{ room.beds }}
                  </p>
                  <p class="room-description-preview">
                    {{
                      room.description ||
                      t("public.roomDetailsAmenitiesAndRatesAreOnTheRoomPage")
                    }}
                  </p>
                  <div class="profile-room-footer">
                    <span
                      ><strong>{{ money(room.price) }}</strong
                      ><small>
                        {{ t("public.nightBeforeSupplements") }}</small
                      ></span
                    ><RouterLink
                      class="secondary button-link"
                      :to="roomLink(room)"
                      >{{ t("public.chooseRoom") }}</RouterLink
                    >
                  </div>
                </div>
              </article>
            </section>
            <section id="reviews" class="profile-section">
              <div class="section-title-row">
                <h2>{{ t("public.guestReviews") }}</h2>
                <span v-if="rating" class="rating">★ {{ rating }}</span>
              </div>
              <p class="field-help">
                {{
                  t("public.leaveAReviewInMyBookingsAfterYourStayIsComplete")
                }}
              </p>
              <div v-if="!reviews.length" class="profile-feedback">
                <h3>{{ t("public.thisPlaceHasNoReviewsYet") }}</h3>
                <p>
                  {{ t("public.shareYourExperienceAndPhotosAfterYourStay") }}
                </p>
              </div>
              <article
                v-for="review in reviews"
                :key="review.id"
                class="public-review"
              >
                <div class="review-heading">
                  <strong>{{ t("public.resortGuest") }}</strong
                  ><span class="rating"
                    >{{ "★".repeat(review.rating)
                    }}<span class="sr-only">
                      {{ review.rating }} {{ t("public.outOf5") }}</span
                    ></span
                  >
                </div>
                <p class="small muted">
                  {{ dateLabel(review.createdAt)
                  }}<span v-if="review.verifiedStay">
                    {{ t("public.verifiedStay") }}</span
                  >
                </p>
                <p class="review-text">{{ review.text }}</p>
                <div v-if="review.photos?.length" class="review-photos">
                  <a
                    v-for="photo in review.photos"
                    :key="photo"
                    :href="photo"
                    target="_blank"
                    rel="noopener noreferrer"
                    :aria-label="t('public.openReviewPhoto')"
                    ><img
                      :src="photo"
                      :alt="t('public.guestReviewPhoto')"
                      loading="lazy"
                  /></a>
                </div>
                <div v-if="review.reply" class="review-reply">
                  <strong>{{ t("public.resortResponse") }}</strong>
                  <p>{{ review.reply }}</p>
                </div>
              </article>
            </section>
            <section id="location" class="profile-section">
              <h2>{{ t("public.location") }}</h2>
              <p class="field-help">
                {{ resort.address }}
                {{ t("public.demoPropertyCoordinatesAreApproximate") }}
              </p>
              <div class="profile-location">
                <GeoMap :points="point" :lat="resort.lat" :lng="resort.lng" />
              </div>
            </section>
          </div>
          <aside class="profile-aside">
            <div class="stay-summary">
              <span class="eyebrow">{{ t("public.aPeacefulBreak") }}</span>
              <h2>{{ t("public.startWithYourPlace") }}</h2>
              <p>
                {{
                  t(
                    "public.chooseDatesAndSendARequestTheManagerWillConfirmYourRoom",
                  )
                }}
              </p>
              <a class="primary button-link" href="#rooms">{{
                t("public.chooseARoom")
              }}</a>
              <div class="policy-summary">
                <h3>{{ t("public.cancellationPolicy") }}</h3>
                <p>
                  {{ t("public.beforeCheckinAt") }}
                  {{ resort.checkInTime || "14:00" }} ({{
                    resort.timeZone || "Asia/Almaty"
                  }}):
                </p>
                <ul>
                  <li>{{ t("public.48HoursOrMore100Refund") }}</li>
                  <li>{{ t("public.24To48Hours70Refund") }}</li>
                  <li>{{ t("public.lessThan24HoursNoRefund") }}</li>
                </ul>
                <p class="small muted">
                  {{
                    t("public.paymentsAndRefundsCurrentlyWorkInDemoModeOnly")
                  }}
                </p>
              </div>
            </div>
          </aside>
        </div>
        <p class="public-data-note">
          {{ t("public.pricesAndLocationsAreIllustrativePhotosMayBeExamples") }}
        </p>
      </template>
    </main>
  </div>
</template>
