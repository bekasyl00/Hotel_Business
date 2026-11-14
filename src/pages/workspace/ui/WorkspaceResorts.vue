<script setup>
import { useI18n } from "vue-i18n";
import { statusNames } from "@/shared/lib";
const { t } = useI18n();
defineProps(["filteredResorts", "accounts", "rooms", "isAdmin"]);
const emit = defineEmits(["open", "confirm", "switch-resort"]);
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
          <th>{{ t("staff.resort") }}</th>
          <th>{{ t("staff.location") }}</th>
          <th>{{ t("staff.rooms") }}</th>
          <th>{{ t("staff.status") }}</th>
          <th>{{ t("staff.actions") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in filteredResorts" :key="r.id">
          <td :data-label="t('staff.resort')">
            <div class="property-cell">
              <img
                src="/assets/resort.jpg"
                :alt="t('staff.resortIllustration')"
              />
              <div>
                <strong>{{ r.name }}</strong
                ><small>{{
                  r.subtitle || t("staff.descriptionMissing")
                }}</small>
                <small v-if="isAdmin"
                  >{{ t("staff.directory.owner") }}:
                  {{
                    accounts.find((a) => a.id === String(r.accountId))?.name ||
                    "—"
                  }}</small
                >
              </div>
            </div>
          </td>
          <td :data-label="t('staff.location')">
            {{ r.city }}<small>{{ r.address }}</small>
          </td>
          <td :data-label="t('staff.rooms')">
            <button class="text-button" @click="emit('switch-resort', r.id)">
              {{
                t("staff.roomsLink", {
                  count: rooms.filter((x) => x.resortId === r.id).length,
                })
              }}
            </button>
          </td>
          <td :data-label="t('staff.status')">
            <span :class="['status-pill', r.status]">{{
              statusNames[r.status]
            }}</span>
          </td>
          <td :data-label="t('staff.actions')">
            <div class="row-actions">
              <button
                v-if="r.status !== 'archived'"
                class="text-button"
                @click="emit('open', 'resorts', r)"
              >
                {{ t("staff.configure") }}</button
              ><button
                v-if="isAdmin && r.status !== 'archived'"
                class="text-button danger"
                @click="
                  emit('confirm', {
                    kind: 'resorts',
                    item: r,
                    title: t('staff.archiveTitle'),
                    text: t('staff.archiveText'),
                  })
                "
              >
                {{ t("staff.archive") }}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
