<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { StaffShell } from "@/widgets/staff-shell";
import { CompanyDetails } from "@/features/company-details";
import { useSessionStore } from "@/entities/session";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
const { t } = useI18n(),
  router = useRouter(),
  session = useSessionStore();
const profile = ref(null),
  resorts = ref([]),
  selected = ref(""),
  loading = ref(false),
  busy = ref(false),
  companyBusy = ref(false),
  error = ref(""),
  notice = ref(""),
  conflict = ref(false);
const roleName = computed(() =>
  t(
    profile.value?.role === "admin"
      ? "staff.admin"
      : profile.value?.role === "accountant"
        ? "common.accounting.role"
        : "staff.manager",
  ),
);
let generation = 0;
async function load() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  conflict.value = false;
  notice.value = "";
  try {
    const data = await request("GET", "/staff-profile");
    if (run === generation) {
      profile.value = data.profile;
      resorts.value = data.resorts;
      if (!data.resorts.some((r) => r.id === selected.value))
        selected.value = data.resorts[0]?.id || "";
    }
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function save() {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  conflict.value = false;
  try {
    const { name, jobTitle, contactPhone, version, accountVersion } =
      profile.value;
    const result = await request("PATCH", "/staff-profile", {
      name,
      jobTitle,
      contactPhone,
      version,
      accountVersion,
    });
    profile.value = result.profile;
    session.user = result.account;
    notice.value = t("common.staffProfile.saved");
  } catch (e) {
    error.value = e.message;
    conflict.value = e.status === 409;
  } finally {
    busy.value = false;
  }
}
async function logout() {
  await session.logout();
  router.replace("/staff/login");
}
onMounted(load);
onBeforeUnmount(() => generation++);
</script>
<template>
  <StaffShell section="profile" @logout="logout"
    ><main class="staff-profile-page">
      <header>
        <span class="eyebrow">{{ t("staff.workspaceEyebrow") }}</span>
        <h1>{{ t("common.staffProfile.title") }}</h1>
        <p>{{ t("common.staffProfile.description") }}</p>
      </header>
      <p v-if="loading" role="status">{{ t("common.staffProfile.loading") }}</p>
      <p v-if="isDemo" class="field-help">
        {{ t("common.staffProfile.demo") }}
      </p>
      <template v-else-if="profile">
        <section class="staff-profile-card">
          <h2>{{ t("common.staffProfile.personalTitle") }}</h2>
          <form class="editor-form" @submit.prevent="save">
            <fieldset :disabled="busy">
              <legend class="profile-sr-only">
                {{ t("common.staffProfile.personalTitle") }}
              </legend>
              <div class="form-grid">
                <label
                  >{{ t("common.staffProfile.name")
                  }}<input
                    v-model.trim="profile.name"
                    maxlength="100"
                    autocomplete="name"
                    required
                /></label>
                <label
                  >{{ t("common.staffProfile.jobTitle")
                  }}<input
                    v-model.trim="profile.jobTitle"
                    maxlength="100"
                    autocomplete="organization-title"
                /></label>
                <label
                  >{{ t("common.staffProfile.phone")
                  }}<input
                    v-model.trim="profile.contactPhone"
                    type="tel"
                    maxlength="30"
                    autocomplete="tel"
                /></label>
                <label
                  >{{ t("common.staffProfile.email")
                  }}<input
                    :value="profile.login"
                    type="email"
                    readonly
                    aria-describedby="staff-email-help"
                /></label>
              </div>
            </fieldset>
            <p id="staff-email-help" class="field-help">
              {{ t("common.staffProfile.emailHint") }}
            </p>
            <p class="field-help">
              {{ t("common.staffProfile.accessRole") }}:
              <strong>{{ roleName }}</strong
              >. {{ t("common.staffProfile.roleHint") }}
            </p>
            <p v-if="error" role="alert" class="form-error">{{ error }}</p>
            <p v-if="notice" role="status" class="profile-notice">
              {{ notice }}
            </p>
            <div class="form-actions">
              <button
                v-if="conflict"
                class="secondary"
                type="button"
                :disabled="busy"
                @click="load"
              >
                {{ t("common.staffProfile.reload") }}</button
              ><button class="primary" :disabled="busy || conflict">
                {{ t(busy ? "staff.saving" : "common.staffProfile.save") }}
              </button>
            </div>
          </form>
        </section>
        <section class="staff-profile-card">
          <h2>{{ t("common.staffProfile.companyTitle") }}</h2>
          <p>{{ t("common.staffProfile.documentsHint") }}</p>
          <label v-if="resorts.length" class="profile-resort-label"
            >{{ t("staff.resort")
            }}<select v-model="selected" :disabled="companyBusy">
              <option
                v-for="resort in resorts"
                :key="resort.id"
                :value="resort.id"
              >
                {{ resort.name }}
              </option>
            </select></label
          >
          <p v-else class="field-help">
            {{ t("common.staffProfile.noResorts") }}
          </p>
          <CompanyDetails
            v-if="selected"
            :key="selected"
            :resort-id="selected"
            @busy="companyBusy = $event"
          />
        </section>
      </template>
      <div v-else-if="error" role="alert">
        <p class="form-error">{{ error }}</p>
        <button class="secondary" @click="load">
          {{ t("common.staffProfile.retry") }}
        </button>
      </div>
    </main></StaffShell
  >
</template>
<style scoped>
.staff-profile-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px;
}
.staff-profile-page header {
  margin-bottom: 24px;
}
.staff-profile-page h1 {
  margin: 8px 0;
  font-size: clamp(26px, 4vw, 38px);
}
.staff-profile-page h2 {
  font-size: 20px;
  margin: 0 0 16px;
}
.staff-profile-page p {
  line-height: 1.5;
}
.staff-profile-card {
  background: #fff;
  border: 1px solid #dbe4de;
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 24px;
}
.staff-profile-card fieldset {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
.staff-profile-card input,
.staff-profile-card select {
  width: 100%;
  min-height: 44px;
  box-sizing: border-box;
}
.staff-profile-card input[readonly] {
  background: #f3f5f3;
  color: #617267;
}
.profile-resort-label {
  display: grid;
  gap: 8px;
  max-width: 440px;
  margin: 20px 0;
}
.profile-resort-label select {
  border: 1px solid #dbe4de;
  background: white;
  border-radius: 9px;
  padding: 10px;
}
.profile-notice {
  color: #245e4e;
}
.profile-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
@media (max-width: 760px) {
  .staff-profile-page {
    padding: 18px 14px;
  }
  .staff-profile-card {
    padding: 16px;
  }
  .staff-profile-card .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
