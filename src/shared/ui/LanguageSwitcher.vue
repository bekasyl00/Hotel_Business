<script setup>
import { useI18n } from "vue-i18n";
import { languages, setLocale } from "@/shared/i18n";
const { locale, t } = useI18n();
</script>
<template>
  <label class="language-switcher"
    ><span class="sr-only">{{ t("common.language") }}</span
    ><select
      :value="locale"
      :aria-label="t('common.language')"
      @change="setLocale($event.target.value)"
    >
      <option
        v-for="language in languages"
        :key="language.value"
        :value="language.value"
      >
        {{ language.label }}
      </option>
    </select></label
  >
</template>
<style scoped>
.language-switcher {
  display: inline-flex;
  flex-shrink: 0;
  max-width: 145px;
}
.language-switcher select {
  font: inherit;
  font-size: 12px;
  min-height: 38px;
  width: 100%;
  border: 1px solid currentColor;
  border-radius: 9px;
  background: transparent;
  color: inherit;
  padding: 6px 24px 6px 10px;
  cursor: pointer;
}
.language-switcher option {
  color: #173e31;
  background: white;
}
</style>
