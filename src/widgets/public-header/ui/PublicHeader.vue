<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { request } from "@/shared/api";
import { LanguageSwitcher } from "@/shared/ui";
import { appSurface, isDemo, publicUrl, staffUrl } from "@/shared/config";
const route = useRoute();
const publicLink = appSurface === "staff" ? "a" : RouterLink;
function destination(path, query) {
  if (appSurface !== "staff") return { to: query ? { path, query } : path };
  const suffix = query ? `?${new URLSearchParams(query)}` : "";
  return { href: `${publicUrl.replace(/\/$/, "")}${path}${suffix}` };
}
const categories = ref([]),
  error = ref("");
async function load() {
  error.value = "";
  try {
    const response = await request("GET", "/categories");
    categories.value = (
      Array.isArray(response) ? response : response.categories || []
    ).map((item) =>
      typeof item === "string"
        ? {
            id: item,
            name:
              {
                wellness: t("public.wellness"),
                family: t("public.forFamilies"),
                premium: t("public.premium"),
                nature: t("public.inNature"),
              }[item] || item,
          }
        : {
            id: item.id || item.code || item.value,
            name: item.name || item.label,
          },
    );
  } catch {
    error.value = t("public.categoriesUnavailable");
  }
}
function categoryLabel(category) {
  const key = {
    wellness: "wellness",
    family: "forFamilies",
    premium: "premium",
    nature: "inNature",
  }[category.id];
  return key ? t(`public.${key}`) : category.name;
}
onMounted(load);
</script>
<template>
  <a class="skip-link" href="#public-main">{{ t("public.skipToContent") }}</a>
  <header class="public-header">
    <div class="public-header-top">
      <component :is="publicLink" class="brand" v-bind="destination('/')"
        ><img src="/assets/logo.svg" alt="" width="36" height="36" /><span
          >тыныс<span class="brand-dot">.</span></span
        ></component
      ><span class="public-brand-note">{{ t("public.timeForYourself") }}</span>
      <nav :aria-label="t('public.mainNavigation')">
        <component
          :is="publicLink"
          v-bind="destination('/')"
          :aria-current="route.path === '/' ? 'page' : undefined"
          >{{ t("public.catalogue") }}</component
        ><component
          :is="publicLink"
          v-bind="destination('/bookings')"
          :aria-current="route.path === '/bookings' ? 'page' : undefined"
          >{{ t("public.myBookings") }}</component
        ><component
          :is="publicLink"
          v-bind="destination('/profile')"
          :aria-current="route.path === '/profile' ? 'page' : undefined"
          >{{ t("public.myProfile") }}</component
        ><a :href="staffUrl || '/staff'" class="public-staff-link">{{
          t("public.staff")
        }}</a>
      </nav>
      <LanguageSwitcher /><span v-if="isDemo" class="demo-badge">{{
        t("public.demo")
      }}</span>
    </div>
    <nav class="category-navigation" :aria-label="t('public.resortCategories')">
      <component
        :is="publicLink"
        v-bind="destination('/')"
        :class="{ selected: route.path === '/' && !route.query.category }"
        >{{ t("public.allResortsInRoomProfilePage") }}</component
      ><component
        :is="publicLink"
        v-for="category in categories"
        :key="category.id"
        v-bind="destination('/', { category: category.id })"
        :class="{
          selected: route.path === '/' && route.query.category === category.id,
        }"
        >{{ categoryLabel(category) }}</component
      ><button v-if="error" class="text-button" @click="load">
        {{ t("public.categoriesUnavailable") }}
        {{ t("public.retryInPublicHeader") }}
      </button>
    </nav>
  </header>
</template>
