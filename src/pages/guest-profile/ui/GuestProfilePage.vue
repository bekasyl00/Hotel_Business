<script setup>
import { reactive, ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { PublicHeader } from "@/widgets/public-header";
import { GuestBookingHistory } from "@/widgets/guest-booking-history";
import { useGuestAccountStore } from "@/entities/guest-account";
import { useBookingStore } from "@/entities/booking";
import { request, ApiError, uploadErrorCode } from "@/shared/api";
import { isDemo, isMobile } from "@/shared/config";
const { t } = useI18n(),
  account = useGuestAccountStore(),
  bookings = useBookingStore();
const data = ref(null),
  loading = ref(true),
  busy = ref(false),
  error = ref(""),
  formError = ref(""),
  saved = ref(false);
const avatarBusy = ref(false),
  avatarError = ref(""),
  avatarSaved = ref(false),
  pendingAvatar = ref(null);
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
async function selectAvatar(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  pendingAvatar.value = file;
  await saveAvatar();
}
async function saveAvatar(remove = false) {
  avatarBusy.value = true;
  avatarError.value = "";
  avatarSaved.value = false;
  try {
    let body;
    if (!remove) {
      const code = uploadErrorCode(pendingAvatar.value);
      if (code) throw new ApiError(null, 422, {}, code);
      body = new FormData();
      body.append("file", pendingAvatar.value);
    }
    const result = await request(
      remove ? "DELETE" : "POST",
      "/profile/avatar",
      body,
    );
    data.value.profile = result.profile;
    if (account.session) account.session.profile = result.profile;
    pendingAvatar.value = null;
    avatarSaved.value = true;
  } catch (e) {
    avatarError.value = e.message;
  } finally {
    avatarBusy.value = false;
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
                  : t(
                      isMobile
                        ? "common.mobile.localHistory"
                        : "auth.guestNotice",
                    )
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
              ><button
                class="secondary"
                :disabled="busy || avatarBusy"
                @click="logout"
              >
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
            <section
              class="guest-avatar-panel"
              :aria-label="t('common.media.avatar')"
              :aria-busy="avatarBusy"
            >
              <img
                v-if="data.profile?.avatarUrl"
                class="guest-avatar"
                :src="data.profile.avatarUrl"
                :alt="t('common.media.avatar')"
              />
              <div
                v-else
                class="guest-avatar guest-avatar-placeholder"
                aria-hidden="true"
              >
                {{ (form.name || "?").slice(0, 1).toUpperCase() }}
              </div>
              <div class="guest-avatar-controls">
                <template v-if="account.authenticated">
                  <label
                    >{{
                      t(
                        data.profile?.avatarUrl
                          ? "common.media.replaceAvatar"
                          : "common.media.addAvatar",
                      )
                    }}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      :disabled="avatarBusy || busy"
                      @change="selectAvatar"
                    />
                  </label>
                  <p class="field-help">{{ t("common.media.imageHint") }}</p>
                  <p v-if="isDemo" class="field-help">
                    {{ t("common.media.demoHint") }}
                  </p>
                  <button
                    v-if="data.profile?.avatarUrl"
                    type="button"
                    class="text-button danger"
                    :disabled="avatarBusy || busy"
                    @click="saveAvatar(true)"
                  >
                    {{ t("common.media.removeAvatar") }}
                  </button>
                  <p v-if="avatarBusy" role="status">
                    {{ t("staff.uploadingFile") }}
                  </p>
                  <p v-if="avatarSaved" role="status" class="success-notice">
                    {{ t("common.media.avatarSaved") }}
                  </p>
                  <p v-if="avatarError" role="alert" class="form-error">
                    {{ avatarError }}
                  </p>
                  <button
                    v-if="avatarError && pendingAvatar"
                    type="button"
                    class="secondary"
                    :disabled="avatarBusy || busy"
                    @click="saveAvatar()"
                  >
                    {{ t("auth.retry") }}
                  </button>
                </template>
                <p v-else class="field-help">
                  {{ t("common.media.avatarAccount") }}
                </p>
              </div>
            </section>
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
              <button class="primary" :disabled="busy || avatarBusy">
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
.guest-avatar-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 18px;
  margin: 20px 0;
}
.guest-avatar {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  object-fit: cover;
  flex: 0 0 88px;
  border: 1px solid #d6e2d2;
}
.guest-avatar-placeholder {
  display: grid;
  place-items: center;
  background: #eef4e9;
  color: #264b36;
  font-size: 32px;
  font-weight: 700;
}
.guest-avatar-controls {
  min-width: 0;
  width: 100%;
}
.guest-avatar-controls label {
  display: grid;
  gap: 8px;
  font-weight: 600;
}
.guest-avatar-controls input {
  width: 100%;
  min-width: 0;
  font-size: 13px;
}
.guest-avatar-controls button {
  margin-top: 8px;
}
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
  .guest-avatar-panel {
    flex-direction: column;
  }
  .profile-account-banner {
    align-items: flex-start;
    flex-direction: column;
  }
  .profile-account-actions {
    width: 100%;
  }
}
</style>
