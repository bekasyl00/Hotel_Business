<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { StaffShell, staffNavigation } from "@/widgets/staff-shell";
import { useSessionStore } from "@/entities/session";
const session = useSessionStore(),
  router = useRouter(),
  error = ref("");
const { t } = useI18n();
const sections = computed(() =>
  staffNavigation(session.user?.role)
    .filter(([path]) => !["overview", "analytics", "bookings"].includes(path))
    .map(([path, icon, label]) => [
      path,
      path === "resorts" && !session.isAdmin ? "staff.myResort" : label,
      icon,
    ]),
);
async function logout() {
  try {
    await session.logout();
    await router.replace("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
</script>
<template>
  <StaffShell section="more" @logout="logout">
    <main class="mobile-management">
      <span class="eyebrow">{{ t("staff.workspaceEyebrow") }}</span>
      <h1>{{ t("common.mobile.manage") }}</h1>
      <p class="muted">
        {{ session.user?.name }} ·
        {{
          session.isAdmin
            ? t("staff.admin")
            : session.isAccountant
              ? t("common.accounting.role")
              : t("staff.manager")
        }}
      </p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="mobile-management-grid">
        <RouterLink
          v-for="[path, label, icon] in sections"
          :key="path"
          :to="'/staff/' + path"
        >
          <span aria-hidden="true">{{ icon }}</span
          ><strong>{{ t(label) }}</strong
          ><span aria-hidden="true">›</span>
        </RouterLink>
      </div>
    </main>
  </StaffShell>
</template>
