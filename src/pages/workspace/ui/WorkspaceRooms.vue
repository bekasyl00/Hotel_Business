<script setup>
import { useI18n } from "vue-i18n";
import { money, statusNames } from "@/shared/lib";
const { t } = useI18n();
defineProps(["filteredRooms"]);
const emit = defineEmits(["open", "confirm"]);
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
          <th>{{ t("staff.physicalRoom") }}</th>
          <th>{{ t("staff.category") }}</th>
          <th>{{ t("staff.capacity") }}</th>
          <th>{{ t("staff.perNight") }}</th>
          <th>{{ t("staff.status") }}</th>
          <th>{{ t("staff.actions") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in filteredRooms" :key="r.id">
          <td :data-label="t('staff.physicalRoom')">
            <strong>№ {{ r.number }}</strong
            ><small>{{ r.area }} {{ t("staff.squareMetres") }}</small>
          </td>
          <td :data-label="t('staff.category')">
            {{ r.title }}<small>{{ r.beds }}</small>
          </td>
          <td :data-label="t('staff.capacity')">
            {{ t("staff.guestCount", { count: r.capacity }) }}
          </td>
          <td :data-label="t('staff.perNight')" class="numeric">
            {{ money(r.price) }}
          </td>
          <td :data-label="t('staff.status')">
            <span :class="['status-pill', r.status]">{{
              statusNames[r.status]
            }}</span>
          </td>
          <td :data-label="t('staff.actions')">
            <div class="row-actions">
              <button class="text-button" @click="emit('open', 'rooms', r)">
                {{ t("staff.edit") }}</button
              ><button
                class="text-button danger"
                @click="
                  emit('confirm', {
                    kind: 'rooms',
                    item: r,
                    title: t('staff.deleteRoomTitle', {
                      number: r.number,
                    }),
                    text: t('staff.deleteRoomText'),
                  })
                "
              >
                {{ t("staff.delete") }}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
