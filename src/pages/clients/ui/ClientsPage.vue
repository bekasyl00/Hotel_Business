<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { StaffShell } from "@/widgets/staff-shell";
import { useSessionStore } from "@/entities/session";
import { request } from "@/shared/api";
const { t } = useI18n(),
  session = useSessionStore(),
  router = useRouter();
const query = ref(""),
  page = ref(1),
  data = ref(null),
  loading = ref(false),
  error = ref("");
let generation = 0;
async function load(reset = false) {
  if (reset) page.value = 1;
  const run = ++generation;
  loading.value = true;
  error.value = "";
  data.value = null;
  try {
    const result = await request(
      "GET",
      `/clients?${new URLSearchParams({ q: query.value, page: page.value })}`,
    );
    if (run === generation) data.value = result;
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function turn(delta) {
  page.value += delta;
  await load();
}
async function logout() {
  try {
    await session.logout();
    await router.replace("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
onMounted(() => load());
</script>
<template>
  <StaffShell section="clients" @logout="logout">
    <main class="work-main">
      <header class="work-title">
        <div>
          <span class="eyebrow">{{ t("staff.platform") }}</span>
          <h1>{{ t("staff.directory.clients") }}</h1>
          <p>{{ t("staff.directory.description") }}</p>
        </div>
      </header>
      <form class="client-search" @submit.prevent="load(true)">
        <label
          >{{ t("staff.directory.search")
          }}<input v-model="query" type="search" maxlength="100" /></label
        ><button class="primary" :disabled="loading">
          {{ t("staff.directory.search") }}
        </button>
      </form>
      <p v-if="loading" role="status">{{ t("staff.loadingGuest") }}</p>
      <div v-else-if="error" role="alert">
        <p>{{ error }}</p>
        <button class="secondary" @click="load()">
          {{ t("staff.retry") }}
        </button>
      </div>
      <template v-else-if="data">
        <p>{{ t("staff.directory.count", { count: data.count }) }}</p>
        <div class="client-grid">
          <article
            v-for="item in data.items"
            :key="item.profile.id"
            class="client-card"
          >
            <h2>{{ item.profile.name || t("staff.websiteGuest") }}</h2>
            <p>{{ item.profile.phone || t("staff.noPhone") }}</p>
            <span class="status-pill" :class="item.account?.status">{{
              item.account
                ? t("staff.directory.registered") +
                  " · " +
                  t(
                    item.account.status === "active"
                      ? "staff.active"
                      : "staff.disabled",
                  )
                : t("staff.directory.legacy")
            }}</span>
            <p>{{ t("staff.directory.bookings") }}: {{ item.bookingCount }}</p>
            <RouterLink
              class="text-button"
              :to="'/staff/guests/' + encodeURIComponent(item.profile.id)"
              >{{ t("staff.directory.open") }} →</RouterLink
            >
          </article>
        </div>
        <div class="client-pagination">
          <button class="secondary" :disabled="page <= 1" @click="turn(-1)">
            {{ t("staff.directory.previous") }}</button
          ><span>{{ page }}</span
          ><button
            class="secondary"
            :disabled="page * data.pageSize >= data.count"
            @click="turn(1)"
          >
            {{ t("staff.directory.next") }}
          </button>
        </div>
      </template>
    </main>
  </StaffShell>
</template>
<style scoped>
.client-search {
  display: flex;
  align-items: end;
  gap: 12px;
  margin: 24px 0;
  flex-wrap: wrap;
}
.client-search label {
  display: grid;
  gap: 8px;
  flex: 1;
  min-width: 180px;
}
.client-search input {
  width: 100%;
  padding: 14px;
  border: 1px solid #dce3dc;
  border-radius: 10px;
}
.client-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
  gap: 16px;
}
.client-card {
  border: 1px solid #dce3dc;
  padding: 24px;
  border-radius: 18px;
  background: white;
  overflow-wrap: anywhere;
}
.client-card h2 {
  font-size: 22px;
}
.client-pagination {
  display: flex;
  gap: 16px;
  align-items: center;
  margin: 24px 0;
}
</style>
