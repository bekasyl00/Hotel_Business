<script setup>
import { RouterView } from "vue-router";
import { useI18n } from "vue-i18n";
import { routeLoadFailed, reloadApplication } from "./route-errors.js";
const { t } = useI18n();
</script>
<template>
  <div v-if="routeLoadFailed" class="route-recovery" role="alert">
    <p>{{ t("common.loadError") }}</p>
    <button @click="reloadApplication">{{ t("common.reload") }}</button>
  </div>
  <RouterView />
</template>
<style>
.route-recovery {
  position: fixed;
  bottom: 18px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  background: #fff5df;
  color: #573d17;
  border: 1px solid #ad7e35;
  padding: 16px;
  border-radius: 14px;
  width: min(520px, calc(100% - 32px));
  box-shadow: 0 10px 40px #0002;
}
.route-recovery button {
  margin-top: 10px;
  background: white;
  border: 1px solid currentColor;
  padding: 8px 12px;
  border-radius: 8px;
  font: inherit;
  color: inherit;
  cursor: pointer;
}
</style>
