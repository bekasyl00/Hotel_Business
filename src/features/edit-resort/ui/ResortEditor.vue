<script setup>
import { reactive } from "vue";
import { Modal, GeoMap } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
const props = defineProps({ item: Object });
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  name: "",
  city: "Сарыагаш",
  address: "",
  subtitle: "",
  description: "",
  feature: "Отдых",
  lat: 41.385,
  lng: 69.061,
  status: "draft",
  ...props.item,
});
const { busy, error, save } = useEditor("resorts", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? 'Настройки санатория' : 'Новый санаторий'"
    wide
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save(form)">
      <div class="form-section">
        <span class="section-number">01</span>
        <h3>Основная информация</h3>
      </div>
      <div class="form-grid">
        <label class="span-2"
          >Название<input
            v-model="form.name"
            required
            maxlength="100"
            placeholder="Например, Altyn Bulak" /></label
        ><label
          >Город<input v-model="form.city" required maxlength="80" /></label
        ><label
          >Адрес<input
            v-model="form.address"
            required
            maxlength="200"
            placeholder="Улица и дом" /></label
        ><label class="span-2"
          >Краткое описание<input
            v-model="form.subtitle"
            maxlength="160"
            placeholder="Чем запомнится отдых здесь" /></label
        ><label class="span-2"
          >Описание<textarea
            v-model="form.description"
            rows="3"
            maxlength="2000"
          ></textarea></label
        ><label
          >Основная услуга<input
            v-model="form.feature"
            maxlength="80"
            required /></label
        ><label
          >Видимость<select v-model="form.status">
            <option value="draft">Черновик</option>
            <option value="published">Опубликован</option>
          </select></label
        >
      </div>
      <p class="field-help">
        Для публикации нужен хотя бы один активный номер и тариф. Новый
        санаторий сначала сохраните как черновик.
      </p>
      <div class="form-section">
        <span class="section-number">02</span>
        <h3>Положение на карте</h3>
      </div>
      <GeoMap
        editable
        :lat="Number(form.lat)"
        :lng="Number(form.lng)"
        @location="Object.assign(form, $event)"
      />
      <div class="form-grid">
        <label
          >Широта<input
            v-model.number="form.lat"
            type="number"
            step="any"
            min="-90"
            max="90"
            required /></label
        ><label
          >Долгота<input
            v-model.number="form.lng"
            type="number"
            step="any"
            min="-180"
            max="180"
            required
        /></label>
      </div>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          class="secondary"
          type="button"
          :disabled="busy"
          @click="emit('close')"
        >
          Отмена</button
        ><button class="primary" :disabled="busy">
          {{ busy ? "Сохраняем…" : "Сохранить санаторий" }}
        </button>
      </div>
    </form></Modal
  >
</template>
