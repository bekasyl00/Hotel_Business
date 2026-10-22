<script setup>
import { useI18n } from "vue-i18n";
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "@/entities/session";
import { request } from "@/shared/api";
import { isDemo, publicUrl } from "@/shared/config";
import { LanguageSwitcher } from "@/shared/ui";
const { t } = useI18n();
const accounts = ref([]),
  accountId = ref(""),
  email = ref(""),
  password = ref(""),
  error = ref(""),
  busy = ref(false),
  loading = ref(true);
const session = useSessionStore(),
  router = useRouter();
async function load() {
  loading.value = true;
  error.value = "";
  try {
    if (isDemo) {
      accounts.value = await request("GET", "/demo/accounts");
      accountId.value = accounts.value[0]?.id || "";
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
async function login() {
  busy.value = true;
  error.value = "";
  try {
    await session.login(
      isDemo
        ? { accountId: accountId.value }
        : { email: email.value, password: password.value },
    );
    password.value = "";
    await router.push("/staff/overview");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <main class="login-page">
    <section class="login-story">
      <a class="staff-brand" :href="publicUrl"
        ><img src="/assets/logo.svg" alt="" width="38" />тыныс.</a
      >
      <div>
        <span class="eyebrow">{{ t("staff.teamEyebrow") }}</span>
        <h1>{{ t("staff.loginHeadline") }}</h1>
        <p>{{ t("staff.loginDescription") }}</p>
      </div>
      <span class="login-bottom">{{ t("staff.loginTagline") }}</span>
    </section>
    <section class="login-panel">
      <div class="login-box">
        <div class="login-language"><LanguageSwitcher /></div>
        <a class="back-link" :href="publicUrl">{{ t("staff.backToResorts") }}</a
        ><span class="eyebrow">{{ t("staff.staffEyebrow") }}</span>
        <h2>{{ t("staff.welcome") }}</h2>
        <p class="muted">
          {{
            isDemo ? t("staff.chooseDemoAccount") : t("staff.loginOrganization")
          }}
        </p>
        <p v-if="loading" role="status">{{ t("staff.loadingAccounts") }}</p>
        <form v-else class="editor-form" @submit.prevent="login">
          <template v-if="isDemo"
            ><label
              >{{ t("staff.demoAccount")
              }}<select v-model="accountId" required>
                <option v-for="a in accounts" :key="a.id" :value="a.id">
                  {{ a.name }} ·
                  {{
                    a.role === "admin"
                      ? t("staff.adminLower")
                      : t("staff.managerLower")
                  }}
                </option>
              </select></label
            >
            <div class="role-explanation">
              <strong>{{
                accounts.find((a) => a.id === accountId)?.role === "admin"
                  ? t("staff.wholePlatform")
                  : t("staff.ownResortOnly")
              }}</strong>
              <p>
                {{
                  accounts.find((a) => a.id === accountId)?.role === "admin"
                    ? t("staff.adminScope")
                    : t("staff.managerScope")
                }}
              </p>
            </div></template
          ><template v-else
            ><label
              >Email<input
                v-model="email"
                type="email"
                autocomplete="username"
                required /></label
            ><label
              >{{ t("staff.password")
              }}<input
                v-model="password"
                type="password"
                autocomplete="current-password"
                required /></label
          ></template>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button
            class="primary full-width"
            :disabled="busy || (isDemo && !accounts.length)"
          >
            {{ busy ? t("staff.signingIn") : t("staff.signIn") }}</button
          ><button v-if="error" type="button" class="text-button" @click="load">
            {{ t("staff.retryLoading") }}
          </button>
        </form>
        <p v-if="isDemo" class="demo-note">
          {{ t("staff.demoLoginNote") }}
        </p>
      </div>
    </section>
  </main>
</template>
<style scoped>
.login-language {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}
</style>
