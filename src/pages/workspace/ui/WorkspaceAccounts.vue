<script setup>
import { useI18n } from "vue-i18n";
import { statusNames } from "@/shared/lib";
const { t } = useI18n();
defineProps(["filteredAccounts", "resorts"]);
const emit = defineEmits(["open"]);
</script>
<template>
  <div
    class="table-scroll"
    tabindex="0"
    role="region"
    :aria-label="t('staff.dataTable')"
  >
    <table class="workspace-table">
      <thead>
        <tr>
          <th>{{ t("staff.managers") }}</th>
          <th>{{ t("staff.resort") }}</th>
          <th>{{ t("staff.access") }}</th>
          <th>{{ t("staff.action") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="a in filteredAccounts" :key="a.id">
          <td :data-label="t('staff.manager')">
            <strong>{{ a.name }}</strong
            ><small>{{ a.login }}</small>
            <small>{{
              a.role === "admin"
                ? t("staff.admin")
                : a.role === "accountant"
                  ? t("common.accounting.role")
                  : t("staff.manager")
            }}</small>
          </td>
          <td :data-label="t('staff.resort')">
            {{
              resorts
                .filter((r) => String(r.accountId) === a.id)
                .map((r) => r.name)
                .join(", ") || "—"
            }}
          </td>
          <td :data-label="t('staff.access')">
            <span :class="['status-pill', a.status]">{{
              statusNames[a.status]
            }}</span>
          </td>
          <td :data-label="t('staff.action')">
            <button
              class="text-button"
              v-if="a.role !== 'admin'"
              @click="emit('open', 'accounts', a)"
            >
              {{ t("staff.configureAccess") }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
