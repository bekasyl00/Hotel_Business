<script setup>
import { reactive } from "vue";
import { Modal } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
import { categoryNames } from "@/shared/lib";
const props = defineProps({ item: Object, resortId: String });
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  resortId: props.resortId,
  number: "",
  category: "standard",
  title: "Стандарт",
  capacity: 2,
  area: 22,
  beds: "Две односпальные кровати",
  price: 24000,
  status: "active",
  ...props.item,
});
const { busy, error, save } = useEditor("rooms", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? 'Редактировать номер' : 'Добавить номер'"
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save(form)">
      <p class="field-help">
        Одна запись — одна физическая комната. Количество комнат считается
        автоматически.
      </p>
      <div class="form-grid">
        <label
          >Номер комнаты<input
            v-model="form.number"
            required
            maxlength="20"
            placeholder="Например, 201" /></label
        ><label
          >Категория<select
            v-model="form.category"
            @change="form.title = categoryNames[form.category]"
          >
            <option
              v-for="(title, key) in categoryNames"
              :key="key"
              :value="key"
            >
              {{ title }}
            </option>
          </select></label
        ><label class="span-2"
          >Название<input v-model="form.title" required maxlength="80" /></label
        ><label
          >Вместимость<input
            v-model.number="form.capacity"
            type="number"
            min="1"
            max="4"
            required /></label
        ><label
          >Площадь, м²<input
            v-model.number="form.area"
            type="number"
            min="5"
            max="500"
            step="0.1"
            required /></label
        ><label class="span-2"
          >Кровати<input v-model="form.beds" required maxlength="120" /></label
        ><label
          >Цена за номер / ночь, ₸<input
            v-model.number="form.price"
            type="number"
            min="0"
            max="10000000"
            step="1"
            required /></label
        ><label
          >Статус<select v-model="form.status">
            <option value="active">Активен</option>
            <option value="maintenance">На обслуживании</option>
          </select></label
        >
      </div>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          @click="emit('close')"
          :disabled="busy"
        >
          Отмена</button
        ><button class="primary" :disabled="busy">
          {{ busy ? "Сохраняем…" : "Сохранить номер" }}
        </button>
      </div>
    </form></Modal
  >
</template>
