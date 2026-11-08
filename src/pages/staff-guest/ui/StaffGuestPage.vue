<script setup>
import { useI18n } from "vue-i18n";
import { ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { StaffShell } from "@/widgets/staff-shell";
import { GuestBookingHistory } from "@/widgets/guest-booking-history";
import { useSessionStore } from "@/entities/session";
import { useResortStore } from "@/entities/resort";
import { useBookingStore } from "@/entities/booking";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
const { t } = useI18n();
const session = useSessionStore(),
  catalog = useResortStore(),
  bookings = useBookingStore(),
  route = useRoute(),
  router = useRouter();
const changing = ref(false),
  confirmAccess = ref(false);
async function changeAccess() {
  changing.value = true;
  try {
    data.value.account = await request(
      "PATCH",
      `/clients/${encodeURIComponent(route.params.id)}`,
      {
        status: data.value.account.status === "active" ? "disabled" : "active",
        version: data.value.account.version,
      },
    );
    confirmAccess.value = false;
  } catch (e) {
    error.value = e.message;
  } finally {
    changing.value = false;
  }
}
const data = ref(null),
  loading = ref(true),
  error = ref("");
let generation = 0;
async function load() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  data.value = null;
  try {
    const result = await request(
      "GET",
      `/guests/${encodeURIComponent(route.params.id)}`,
    );
    if (run === generation) data.value = result;
  } catch (e) {
    if (run === generation)
      error.value =
        e.status === 404 || e.status === 403
          ? t("staff.guestUnavailableText")
          : e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function logout() {
  try {
    await session.logout();
    catalog.clear();
    bookings.items = [];
    router.replace("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
watch(() => route.params.id, load, { immediate: true });
</script>
<template>
  <StaffShell
    :section="session.isAdmin ? 'clients' : 'bookings'"
    @logout="logout"
    ><main class="work-main staff-guest-main">
      <RouterLink
        class="profile-back"
        :to="session.isAdmin ? '/staff/clients' : '/staff/bookings'"
        >{{
          t(
            session.isAdmin
              ? "staff.directory.clients"
              : "staff.backToBookings",
          )
        }}</RouterLink
      >
      <div v-if="isDemo" class="demo-strip">
        {{ t("staff.demoGuest") }}
      </div>
      <div v-if="loading" class="profile-feedback" role="status">
        {{ t("staff.loadingGuest") }}
      </div>
      <div v-else-if="error" class="profile-feedback" role="alert">
        <h1>{{ t("staff.profileUnavailable") }}</h1>
        <p>{{ error }}</p>
        <button class="secondary" @click="load">{{ t("staff.retry") }}</button>
      </div>
      <template v-else-if="data"
        ><header class="work-title">
          <div>
            <span class="eyebrow">{{ t("staff.guestEyebrow") }}</span>
            <h1>{{ data.profile.name || t("staff.websiteGuest") }}</h1>
            <p>{{ data.profile.phone || t("staff.noPhone") }}</p>
          </div>
        </header>
        <p class="public-session-note">
          {{
            session.isAdmin
              ? t("staff.guestPlatformHistory")
              : t("staff.guestScopedHistory")
          }}
          {{ t("staff.guestEditsContact") }}
        </p>
        <section
          v-if="session.isAdmin && data.account"
          class="public-session-note"
        >
          <h2>{{ t("staff.directory.access") }}</h2>
          <p>
            {{
              t(
                data.account.status === "active"
                  ? "staff.active"
                  : "staff.disabled",
              )
            }}
          </p>
          <button
            v-if="!confirmAccess"
            class="secondary"
            @click="confirmAccess = true"
          >
            {{
              t(
                data.account.status === "active"
                  ? "staff.directory.disable"
                  : "staff.directory.enable",
              )
            }}
          </button>
          <div v-else>
            <p>{{ t("staff.directory.accessHelp") }}</p>
            <button class="primary" :disabled="changing" @click="changeAccess">
              {{ t("staff.directory.confirm") }}
            </button>
            <button
              class="secondary"
              :disabled="changing"
              @click="confirmAccess = false"
            >
              {{ t("staff.directory.cancel") }}
            </button>
          </div>
        </section>
        <GuestBookingHistory :bookings="data.bookings" staff
      /></template></main
  ></StaffShell>
</template>
