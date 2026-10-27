<script setup>
import { useI18n } from "vue-i18n";
import { onMounted, onBeforeUnmount, ref, useId } from "vue";
const { t } = useI18n();
const props = defineProps({ title: String, wide: Boolean, busy: Boolean });
const emit = defineEmits(["close"]);
const dialog = ref();
const titleId = useId();
let previous;
onMounted(() => {
  previous = document.activeElement;
  dialog.value.showModal();
});
onBeforeUnmount(() => {
  dialog.value?.close();
  previous?.isConnected && previous.focus();
});
</script>
<template>
  <Teleport to="body"
    ><dialog
      ref="dialog"
      :class="['app-dialog', { wide }]"
      :aria-labelledby="titleId"
      @cancel.prevent="!busy && emit('close')"
    >
      <div class="modal-heading">
        <div>
          <span class="eyebrow">ТЫНЫС</span>
          <h2 :id="titleId">{{ title }}</h2>
        </div>
        <button
          class="icon-button"
          type="button"
          :aria-label="t('staff.close')"
          :disabled="busy"
          @click="emit('close')"
        >
          ×
        </button>
      </div>
      <slot /></dialog
  ></Teleport>
</template>
