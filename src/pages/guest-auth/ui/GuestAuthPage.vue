<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { PublicHeader } from "@/widgets/public-header";
import { useGuestAccountStore } from "@/entities/guest-account";
import { useBookingStore } from "@/entities/booking";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
const { t } = useI18n(),
  route = useRoute(),
  router = useRouter(),
  account = useGuestAccountStore(),
  bookings = useBookingStore();
const action = computed(() => route.meta.authAction || "login"),
  title = computed(() =>
    t(
      action.value === "register"
        ? "auth.titleRegister"
        : action.value === "reset"
          ? "auth.titleReset"
          : "auth.titleLogin",
    ),
  );
const form = reactive({
  phone: "",
  name: "",
  password: "",
  confirm: "",
  code: "",
});
const challenge = ref(null),
  busy = ref(false),
  error = ref(""),
  notice = ref(""),
  show = ref(false),
  retryAt = ref(0),
  clock = ref(Date.now());
const remaining = computed(() =>
  Math.max(0, Math.ceil((retryAt.value - clock.value) / 1000)),
);
let generation = 0;
const timer = setInterval(() => (clock.value = Date.now()), 1000);
onBeforeUnmount(() => {
  generation++;
  clearInterval(timer);
});
watch(action, () => {
  generation++;
  busy.value = false;
  retryAt.value = 0;
  challenge.value = null;
  form.password = "";
  form.confirm = "";
  form.code = "";
  error.value = "";
  notice.value = "";
  show.value = false;
});
function normalizedPhone() {
  let phone = form.phone.replace(/[\s()-]/g, "");
  if (/^8\d{10}$/.test(phone)) phone = "+7" + phone.slice(1);
  if (!/^\+77\d{9}$/.test(phone)) throw new Error(t("auth.phoneInvalid"));
  return phone;
}
async function sendCode() {
  const current = ++generation,
    purpose = action.value;
  busy.value = true;
  error.value = "";
  try {
    const result = await request("POST", "/guest-auth/challenges", {
      phone: normalizedPhone(),
      purpose,
    });
    if (current !== generation) return;
    challenge.value = result;
    clock.value = Date.now();
    retryAt.value = clock.value + result.retryAfterSeconds * 1000;
    form.code = "";
  } catch (e) {
    if (current === generation) error.value = e.message;
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function submit() {
  if (action.value !== "login" && !challenge.value) {
    await sendCode();
    return;
  }
  const current = ++generation;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    if (action.value === "login")
      await account.login({
        phone: normalizedPhone(),
        password: form.password,
      });
    else {
      if (form.password !== form.confirm)
        throw new Error(t("auth.passwordMismatch"));
      const payload = {
        challengeId: challenge.value.challengeId,
        code: form.code,
        password: form.password,
      };
      if (action.value === "register")
        await account.register({ ...payload, name: form.name.trim() });
      else {
        await request("POST", "/guest-auth/reset", payload);
        account.clear();
        bookings.items = [];
        if (current !== generation) return;
        form.password = "";
        form.confirm = "";
        form.code = "";
        challenge.value = null;
        notice.value = "auth.resetDone";
        return;
      }
    }
    bookings.items = [];
    if (current !== generation) return;
    form.password = "";
    form.confirm = "";
    await router.replace("/profile");
  } catch (e) {
    if (current === generation) error.value = e.message;
  } finally {
    if (current === generation) busy.value = false;
  }
}
</script>
<template>
  <div class="public-site">
    <PublicHeader />
    <main id="public-main" class="guest-auth-main">
      <RouterLink to="/" class="profile-back">{{ t("auth.back") }}</RouterLink>
      <section class="guest-auth-card">
        <span class="eyebrow">ТЫНЫС</span>
        <h1>{{ title }}</h1>
        <p class="muted">{{ t("auth.subtitle") }}</p>
        <p class="demo-note">{{ t("auth.demoNotice") }}</p>
        <p v-if="isDemo" class="field-help">{{ t("auth.demoLocal") }}</p>
        <form class="editor-form" @submit.prevent="submit">
          <label
            >{{ t("auth.phone")
            }}<input
              v-model="form.phone"
              type="tel"
              autocomplete="tel"
              inputmode="tel"
              required
              maxlength="32"
              placeholder="+7 700 000 00 01"
              :readonly="!!challenge"
              :aria-describedby="'guest-phone-help'"
          /></label>
          <p id="guest-phone-help" class="field-help">
            {{ t("auth.phoneHint") }}
          </p>
          <template v-if="challenge"
            ><button
              class="text-button"
              type="button"
              :disabled="busy"
              @click="
                challenge = null;
                form.code = '';
              "
            >
              {{ t("auth.changePhone") }}
            </button>
            <p v-if="challenge.mode === 'demo'" class="demo-code" role="status">
              {{ t("auth.demoCode", { code: challenge.demoCode }) }}
            </p>
            <label
              >{{ t("auth.code")
              }}<input
                v-model="form.code"
                inputmode="numeric"
                autocomplete="one-time-code"
                pattern="[0-9]{6}"
                maxlength="6"
                required
            /></label>
            <p class="field-help">{{ t("auth.codeHint") }}</p>
            <button
              class="text-button"
              type="button"
              :disabled="busy || remaining > 0"
              @click="sendCode"
            >
              {{
                remaining
                  ? t("auth.waitResend", { seconds: remaining })
                  : t("auth.resend")
              }}
            </button></template
          >
          <label v-if="action === 'register' && challenge"
            >{{ t("auth.name")
            }}<input
              v-model="form.name"
              required
              maxlength="80"
              :autocomplete="isDemo ? 'off' : 'name'"
          /></label>
          <template v-if="action === 'login' || challenge"
            ><label
              >{{ t(action === "reset" ? "auth.newPassword" : "auth.password")
              }}<input
                v-model="form.password"
                :type="show ? 'text' : 'password'"
                required
                :minlength="action === 'login' ? 1 : 12"
                maxlength="128"
                :autocomplete="
                  action === 'login' ? 'current-password' : 'new-password'
                "
                :aria-describedby="
                  action === 'login' ? undefined : 'guest-password-help'
                " /></label
            ><button
              type="button"
              class="text-button"
              :aria-pressed="show"
              @click="show = !show"
            >
              {{ t(show ? "auth.hidePassword" : "auth.showPassword") }}
            </button>
            <p
              v-if="action !== 'login'"
              id="guest-password-help"
              class="field-help"
            >
              {{ t("auth.passwordHint") }}
            </p>
            <label v-if="action !== 'login'"
              >{{ t("auth.confirmPassword")
              }}<input
                v-model="form.confirm"
                :type="show ? 'text' : 'password'"
                required
                minlength="12"
                maxlength="128"
                autocomplete="new-password" /></label
          ></template>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <p v-if="notice" class="success-notice" role="status">
            {{ t(notice) }}
          </p>
          <button class="primary" :disabled="busy">
            {{
              busy
                ? t("auth.busy")
                : action === "login"
                  ? t("auth.signIn")
                  : !challenge
                    ? t("auth.sendCode")
                    : action === "register"
                      ? t("auth.signUp")
                      : t("auth.reset")
            }}
          </button>
        </form>
        <nav class="guest-auth-links">
          <RouterLink v-if="action === 'login'" to="/account/reset-password">{{
            t("auth.forgot")
          }}</RouterLink
          ><RouterLink v-if="action !== 'register'" to="/account/register">{{
            t("auth.signUp")
          }}</RouterLink
          ><RouterLink v-if="action !== 'login'" to="/account/login">{{
            t("auth.signIn")
          }}</RouterLink>
        </nav>
      </section>
    </main>
  </div>
</template>
<style scoped>
.guest-auth-main {
  max-width: 560px;
  margin: 0 auto;
  padding: 32px 20px 80px;
}
.guest-auth-card {
  margin-top: 25px;
  padding: 32px;
  border: 1px solid #dce3db;
  border-radius: 24px;
  background: white;
  display: grid;
  gap: 16px;
}
.guest-auth-card h1 {
  font-size: 32px;
  line-height: 1.2;
}
.guest-auth-links {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 14px;
}
.text-button {
  border: 0;
  background: transparent;
  color: #215b48;
  text-decoration: underline;
  font: inherit;
  text-align: left;
  padding: 4px 0;
  cursor: pointer;
}
.text-button:disabled {
  color: #58645d;
  cursor: default;
}
.demo-code {
  background: #edf3e9;
  border: 1px dashed #638467;
  padding: 14px;
  border-radius: 12px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
.guest-auth-card input[readonly] {
  background: #f2f4f0;
}
@media (max-width: 550px) {
  .guest-auth-card {
    padding: 22px;
  }
  .guest-auth-card h1 {
    font-size: 27px;
  }
}
</style>
