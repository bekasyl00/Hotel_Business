<script setup>
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "@/entities/session";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
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
      <RouterLink class="staff-brand" to="/"
        ><img src="/assets/logo.svg" alt="" width="38" />тыныс.</RouterLink
      >
      <div>
        <span class="eyebrow">ДЛЯ КОМАНДЫ САНАТОРИЯ</span>
        <h1>
          Хороший отдых <br />
          начинается <br />
          с порядка.
        </h1>
        <p>
          Номера, тарифы и бронирования —<br />в одном рабочем пространстве.
        </p>
      </div>
      <span class="login-bottom"
        >С заботой о гостях. С вниманием к деталям.</span
      >
    </section>
    <section class="login-panel">
      <div class="login-box">
        <RouterLink class="back-link" to="/"
          >← Вернуться к санаториям</RouterLink
        ><span class="eyebrow">КАБИНЕТ СОТРУДНИКА</span>
        <h2>Добро пожаловать</h2>
        <p class="muted">
          {{
            isDemo
              ? "Выберите рабочий демо-аккаунт."
              : "Войдите в аккаунт вашей организации."
          }}
        </p>
        <p v-if="loading" role="status">Загружаем аккаунты…</p>
        <form v-else class="editor-form" @submit.prevent="login">
          <template v-if="isDemo"
            ><label
              >Демо-аккаунт<select v-model="accountId" required>
                <option v-for="a in accounts" :key="a.id" :value="a.id">
                  {{ a.name }} ·
                  {{ a.role === "admin" ? "администратор" : "управляющий" }}
                </option>
              </select></label
            >
            <div class="role-explanation">
              <strong>{{
                accounts.find((a) => a.id === accountId)?.role === "admin"
                  ? "Вся платформа"
                  : "Только свой санаторий"
              }}</strong>
              <p>
                {{
                  accounts.find((a) => a.id === accountId)?.role === "admin"
                    ? "Создание санаториев, настройка номеров и управление доступами."
                    : "Номера, тарифы, брони и история закреплённого санатория."
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
              >Пароль<input
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
            {{ busy ? "Входим…" : "Войти в кабинет →" }}</button
          ><button v-if="error" type="button" class="text-button" @click="load">
            Повторить загрузку
          </button>
        </form>
        <p v-if="isDemo" class="demo-note">
          Демонстрационный режим. Пароль не требуется. Данные сохраняются в этом
          браузере; настоящая авторизация появится после подключения бэкенда.
        </p>
      </div>
    </section>
  </main>
</template>
