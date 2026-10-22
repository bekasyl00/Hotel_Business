<script setup>
import { reactive, ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { PublicHeader } from "@/widgets/public-header";
import { GuestBookingHistory } from "@/widgets/guest-booking-history";
import { useGuestAccountStore } from "@/entities/guest-account";
import { useBookingStore } from "@/entities/booking";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
const { t } = useI18n(),
  account = useGuestAccountStore(),
  bookings = useBookingStore();
const data = ref(null),
  loading = ref(true),
  busy = ref(false),
  error = ref(""),
  formError = ref(""),
  saved = ref(false);
const form = reactive({ name: "", phone: "" });
async function load() {
  loading.value = true;
  error.value = "";
  data.value = null;
  try {
    await account.restore();
    data.value = await request("GET", "/profile");
    form.name = data.value.profile?.name || "";
    form.phone = data.value.profile?.phone || "";
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
async function save() {
  busy.value = true;
  formError.value = "";
  saved.value = false;
  try {
    data.value = await request("PATCH", "/profile", {
      name: form.name.trim(),
      phone: form.phone.trim(),
    });
    saved.value = true;
  } catch (e) {
    formError.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function logout() {
  busy.value = true;
  error.value = "";
  try {
    await account.logout();
    bookings.items = [];
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="public-site">
    <PublicHeader />
    <main id="public-main" class="profile-main guest-profile-main">
      <header class="profile-heading">
        <div>
          <span class="eyebrow">ТЫНЫС</span>
          <h1>{{ t("auth.profile") }}</h1>
          <p>{{ t("auth.profileSubtitle") }}</p>
        </div>
        <RouterLink class="secondary button-link" to="/bookings">{{
          t("auth.bookings")
        }}</RouterLink>
      </header>
      <div v-if="loading" class="profile-feedback" role="status">
        {{ t("auth.loading") }}
      </div>
      <div v-else-if="error" class="profile-feedback" role="alert">
        <p>{{ error }}</p>
        <button class="secondary" @click="load">{{ t("auth.retry") }}</button>
      </div>
      <template v-else-if="data"
        ><section class="profile-account-banner">
          <div>
            <strong>{{
              t(account.authenticated ? "auth.account" : "auth.noAccount")
            }}</strong>
            <p>
              {{
                account.authenticated
                  ? isDemo
                    ? t("auth.demoLocal")
                    : t("auth.crossDevice")
                  : t("auth.guestNotice")
              }}
            </p>
            <p v-if="account.authenticated">
              {{ account.session.account.phone }} · {{ t("auth.verified") }}
            </p>
          </div>
          <div class="profile-account-actions">
            <template v-if="!account.authenticated"
              ><RouterLink class="primary button-link" to="/account/register">{{
                t("auth.signUp")
              }}</RouterLink
              ><RouterLink class="secondary button-link" to="/account/login">{{
                t("auth.signIn")
              }}</RouterLink></template
            ><template v-else
              ><RouterLink to="/account/reset-password">{{
                t("auth.titleReset")
              }}</RouterLink
              ><button class="secondary" :disabled="busy" @click="logout">
                {{ t("auth.logout") }}
              </button></template
            >
          </div>
        </section>
        <div class="guest-profile-columns">
          <section class="guest-contact-panel">
            <h2>{{ t("auth.contact") }}</h2>
            <p
              v-if="isDemo || account.session?.mode === 'demo'"
              class="demo-note"
            >
              {{ t("auth.demoNotice") }}
            </p>
            <form class="editor-form" @submit.prevent="save">
              <label
                >{{ t("auth.name")
                }}<input
                  v-model="form.name"
                  required
                  maxlength="80"
                  :autocomplete="isDemo ? 'off' : 'name'" /></label
              ><label
                >{{ t("auth.phone")
                }}<input
                  v-model="form.phone"
                  type="tel"
                  required
                  maxlength="30"
                  :readonly="account.authenticated"
                  :autocomplete="isDemo ? 'off' : 'tel'"
              /></label>
              <p v-if="account.authenticated" class="field-help">
                {{ t("auth.phoneLocked") }}
              </p>
              <p v-if="formError" class="form-error" role="alert">
                {{ formError }}
              </p>
              <p v-if="saved" class="success-notice" role="status">
                {{ t("auth.saved") }}
              </p>
              <button class="primary" :disabled="busy">
                {{ t(busy ? "auth.busy" : "auth.save") }}
              </button>
            </form>
          </section>
          <section class="guest-history-panel">
            <h2>{{ t("auth.history") }}</h2>
            <p class="field-help">
              {{ t("auth.historyCount", { count: data.bookings.length }) }}
            </p>
            <GuestBookingHistory :bookings="data.bookings" />
          </section></div
      ></template>
    </main>
  </div>
</template>
<style scoped>
.profile-account-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  padding: 22px;
  margin: 22px 0;
  background: #eef4e9;
  border: 1px solid #d6e2d2;
  border-radius: 18px;
}
.profile-account-banner p {
  margin-top: 8px;
  max-width: 680px;
  line-height: 1.6;
  font-size: 14px;
}
.profile-account-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.profile-account-actions a,
.profile-account-actions button {
  white-space: nowrap;
}
@media (max-width: 700px) {
  .profile-account-banner {
    align-items: flex-start;
    flex-direction: column;
  }
  .profile-account-actions {
    width: 100%;
  }
}
</style>
