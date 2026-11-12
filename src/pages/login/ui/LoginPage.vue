<script setup>
import { useI18n } from "vue-i18n";
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useSessionStore } from "@/entities/session";
import { request } from "@/shared/api";
import { isDemo, publicUrl, isStaffApp } from "@/shared/config";
import { pendingPushTarget, initStaffPushListeners } from "@/shared/native";
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
  route = useRoute(),
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
    const nextUrl =
      typeof route.query.next === "string" &&
      route.query.next.startsWith("/staff/") &&
      !route.query.next.startsWith("/staff/login")
        ? route.query.next
        : "";
    if (!session.isAccountant && pendingPushTarget.value?.bookingId) {
      const target = pendingPushTarget.value;
      await router.push({
        path: "/staff/bookings",
        query: {
          bookingId: target.bookingId,
          ...(target.resortId ? { resortId: target.resortId } : {}),
          ...(target.notificationId
            ? { notificationId: target.notificationId }
            : {}),
        },
      });
    } else if (nextUrl && !session.isAccountant) {
      await router.push(nextUrl);
    } else {
      await router.push(
        session.isAccountant ? "/staff/accounting" : "/staff/bookings",
      );
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(() => {
  initStaffPushListeners();
  load();
});
</script>
<template>
  <main class="login-page">
    <section class="login-story">
      <a class="staff-brand" :href="isStaffApp ? '/staff/login' : publicUrl"
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
        <div v-if="isStaffApp" class="staff-app-brand">
          <img src="/assets/logo.svg" alt="" width="44" height="44" /><strong>{{
            t("common.mobile.teamTitle")
          }}</strong>
        </div>
        <div class="login-language"><LanguageSwitcher /></div>
        <a v-if="!isStaffApp" class="back-link" :href="publicUrl">{{
          t("staff.backToResorts")
        }}</a
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
        <section class="partner-contact">
          <h3>{{ t("staff.directory.partnerTitle") }}</h3>
          <p>{{ t("staff.directory.partnerDescription") }}</p>
          <a
            class="secondary button-link"
            :href="
              'https://wa.me/77782764005?text=' +
              encodeURIComponent(t('staff.directory.partnerMessage'))
            "
            target="_blank"
            rel="noopener noreferrer"
            >{{ t("staff.directory.contact") }}</a
          >
          <small>+7 778 276 40 05 · Бекасыл Админ</small>
        </section>
        <p v-if="isDemo" class="demo-note">
          {{
            t(
              isStaffApp
                ? "common.mobile.staffDemoLocal"
                : "staff.demoLoginNote",
            )
          }}
        </p>
      </div>
    </section>
  </main>
</template>
<style scoped>
.partner-contact {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #dce3dc;
}
.partner-contact h3 {
  font-size: 20px;
  margin: 0 0 10px;
}
.partner-contact p {
  color: #647269;
  line-height: 1.55;
}
.partner-contact small {
  display: block;
  margin-top: 12px;
}
.login-language {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}
</style>
