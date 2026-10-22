<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import {
  computed,
  onMounted,
  onBeforeUnmount,
  ref,
  watch,
  nextTick,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import { useResortStore } from "@/entities/resort";
import { PublicHeader } from "@/widgets/public-header";
import { GeoMap } from "@/shared/ui";
import { money } from "@/shared/lib";
const catalog = useResortStore(),
  route = useRoute(),
  router = useRouter();
const query = ref(""),
  resortClass = ref("all"),
  sort = ref("recommended"),
  selected = ref(null),
  loading = ref(true),
  error = ref("");
const mapOpen = ref(false),
  mapDialog = ref(null);
let mapTrigger, previousOverflow;
function showMap(id = selected.value) {
  selected.value = id;
  mapTrigger = document.activeElement;
  mapOpen.value = true;
}
watch(mapOpen, async (open) => {
  if (open) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    await nextTick();
    if (mapOpen.value) mapDialog.value?.showModal();
  } else {
    document.body.style.overflow = previousOverflow || "";
    await nextTick();
    if (mapTrigger?.isConnected) mapTrigger.focus();
  }
});
onBeforeUnmount(() => {
  if (mapOpen.value) document.body.style.overflow = previousOverflow || "";
});
const category = computed(() => String(route.query.category || "all"));
const cover = (r) =>
  r.media?.find((m) => m.kind === "image")?.url || "/assets/resort.jpg";
const filtered = computed(() => {
  let items = catalog.resorts
    .filter(
      (r) =>
        (category.value === "all" || r.category === category.value) &&
        (resortClass.value === "all" || r.resortClass === resortClass.value) &&
        `${r.name} ${r.city} ${r.address}`
          .toLocaleLowerCase()
          .includes(query.value.toLocaleLowerCase()),
    )
    .map((r) => {
      const rooms = catalog.rooms.filter(
        (x) => x.resortId === r.id && x.status === "active",
      );
      return {
        ...r,
        price: rooms.length ? Math.min(...rooms.map((x) => x.price)) : null,
        roomCount: rooms.length,
      };
    });
  if (sort.value === "price")
    items.sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
  if (sort.value === "rating")
    items.sort((a, b) => (b.reviewRating ?? 0) - (a.reviewRating ?? 0));
  return items;
});
const points = computed(() =>
  filtered.value.map((r) => ({
    ...r,
    label: r.price === null ? r.name : t("public.from", [money(r.price)]),
  })),
);
const chosen = computed(() =>
  filtered.value.find((r) => r.id === selected.value),
);
async function load() {
  loading.value = true;
  error.value = "";
  try {
    await catalog.loadPublic();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
function reset() {
  query.value = "";
  resortClass.value = "all";
  router.replace({ path: "/" });
}
const storageChanged = (e) => {
  if (e.key === "tynys:workspace:v2") load();
};
onMounted(() => {
  load();
  window.addEventListener("storage", storageChanged);
});
onBeforeUnmount(() => window.removeEventListener("storage", storageChanged));
</script>
<template>
  <div class="public-site discovery-page">
    <PublicHeader />
    <main id="public-main">
      <section class="discovery-search" :aria-label="t('public.findAResort')">
        <div>
          <span class="eyebrow">{{
            t("public.yourBreakStartsWithAPlace")
          }}</span>
          <h1>{{ t("public.findYourResort") }}</h1>
          <p>
            {{ t("public.chooseAPlaceSelectDatesAndARoomOnItsResortPage") }}
          </p>
        </div>
        <label class="discovery-search-input"
          ><span class="sr-only">{{ t("public.cityOrResort") }}</span
          ><span aria-hidden="true">⌕</span
          ><input
            v-model="query"
            type="search"
            :placeholder="t('public.cityResortOrAddress')"
        /></label>
      </section>
      <div class="discovery-layout catalogue-grid-layout">
        <section class="discovery-results" :aria-label="t('public.resortList')">
          <div class="results-heading">
            <strong>{{
              loading
                ? t("public.loading")
                : t("public.resorts", [filtered.length])
            }}</strong
            ><span class="small muted">{{ t("public.openMapToExplore") }}</span>
          </div>
          <div class="discovery-filters">
            <label
              ><span class="sr-only">{{ t("public.resortClass") }}</span
              ><select v-model="resortClass">
                <option value="all">{{ t("public.allClasses") }}</option>
                <option value="standard">{{ t("public.standard") }}</option>
                <option value="comfort">{{ t("public.comfort") }}</option>
                <option value="premium">{{ t("public.premium") }}</option>
              </select></label
            >
            <label
              ><span class="sr-only">{{ t("public.sortBy") }}</span
              ><select v-model="sort">
                <option value="recommended">
                  {{ t("public.recommended") }}
                </option>
                <option value="price">
                  {{ t("public.lowestPriceFirst") }}
                </option>
                <option value="rating">{{ t("public.highestRated") }}</option>
              </select></label
            >
          </div>
          <div v-if="error" class="profile-feedback" role="alert">
            <p>{{ error }}</p>
            <button class="secondary" @click="load">
              {{ t("public.retry") }}
            </button>
          </div>
          <div v-else-if="loading" class="profile-feedback" role="status">
            {{ t("public.loadingResortsAndRooms") }}
          </div>
          <div v-else-if="!filtered.length" class="profile-feedback">
            <h2>{{ t("public.nothingFound") }}</h2>
            <p>{{ t("public.tryAnotherNameOrCategory") }}</p>
            <button class="secondary" @click="reset">
              {{ t("public.resetFilters") }}
            </button>
          </div>
          <div class="catalogue-cards">
            <article
              v-for="r in filtered"
              :key="r.id"
              :class="['discovery-card', { selected: selected === r.id }]"
            >
              <RouterLink :to="`/resorts/${r.id}`" class="discovery-card-image"
                ><img
                  :src="cover(r)"
                  :alt="
                    r.media?.length
                      ? r.name
                      : t('public.illustrativeResortImage')
                  "
                  loading="lazy"
              /></RouterLink>
              <div class="discovery-card-content">
                <div class="card-title-row">
                  <RouterLink :to="`/resorts/${r.id}`"
                    ><h2>{{ r.name }}</h2></RouterLink
                  ><span v-if="r.reviewCount" class="rating"
                    >★ {{ r.reviewRating }}</span
                  >
                </div>
                <p class="small muted">{{ r.city }} · {{ r.address }}</p>
                <p class="discovery-summary">
                  {{ r.subtitle || r.description }}
                </p>
                <div class="discovery-meta">
                  <span>{{
                    {
                      standard: t("public.standard"),
                      comfort: t("public.comfort"),
                      premium: t("public.premium"),
                    }[r.resortClass] || t("public.standard")
                  }}</span
                  ><span
                    >{{ t("public.checkinFrom") }}
                    {{ r.checkInTime || "14:00" }}</span
                  >
                </div>
                <div class="discovery-card-bottom">
                  <strong
                    >{{
                      r.price === null
                        ? t("public.roomsToBeConfirmed")
                        : t("public.from", [money(r.price)])
                    }}<small v-if="r.price !== null">
                      {{ t("public.night") }}</small
                    ></strong
                  ><button
                    class="text-button"
                    :aria-label="t('public.showOnTheMap', [r.name])"
                    @click="showMap(r.id)"
                  >
                    {{ t("public.onTheMap") }}
                  </button>
                </div>
              </div>
            </article>
          </div>
          <p class="public-data-note">
            {{
              t(
                "public.thisCatalogueContainsDemoPropertiesApproximateLocationsAndIllustrativePhotosAvailabilityIs",
              )
            }}
          </p>
        </section>
      </div>
      <button
        class="floating-map-button"
        type="button"
        aria-haspopup="dialog"
        :aria-expanded="mapOpen"
        @click="showMap()"
      >
        <span aria-hidden="true">⌖</span>{{ t("public.openMap") }}
      </button>
      <Teleport to="body"
        ><dialog
          v-if="mapOpen"
          ref="mapDialog"
          class="floating-map-dialog"
          aria-labelledby="catalogue-map-title"
          @cancel.prevent="mapOpen = false"
        >
          <header>
            <div>
              <h2 id="catalogue-map-title">{{ t("public.searchMap") }}</h2>
              <p>{{ t("public.resorts", [filtered.length]) }}</p>
            </div>
            <button
              class="icon-button"
              type="button"
              :aria-label="t('public.closeMap')"
              @click="mapOpen = false"
            >
              ×
            </button>
          </header>
          <section
            class="floating-map-canvas"
            :aria-label="t('public.searchMap')"
          >
            <GeoMap
              :points="points"
              :selected="selected"
              @select="selected = $event"
            />
            <div v-if="chosen" class="map-selection">
              <button
                class="icon-button"
                :aria-label="t('public.closeMapCard')"
                @click="selected = null"
              >
                ×</button
              ><span class="eyebrow">{{ t("public.yourPlaceOnTheMap") }}</span>
              <h2>{{ chosen.name }}</h2>
              <p>{{ chosen.city }} · {{ chosen.address }}</p>
              <RouterLink
                class="primary button-link"
                :to="`/resorts/${chosen.id}`"
                >{{ t("public.viewResort") }}</RouterLink
              >
            </div>
            <div v-else class="discovery-map-label">
              {{ t("public.selectAResortOnTheMap") }}
            </div>
          </section>
        </dialog></Teleport
      >
    </main>
  </div>
</template>
