<script setup>
import { reactive } from "vue";
import { Modal } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
const props = defineProps({ item: Object, resortId: String });
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  resortId: props.resortId,
  name: "",
  description: "",
  supplement: 0,
  status: "active",
  ...props.item,
  features: props.item?.features.join("\n") || "",
});
const { busy, error, save } = useEditor("tariffs", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? 'Редактировать тариф' : 'Добавить тариф'"
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save(form)">
      <label
        >Название<input
          v-model="form.name"
          required
          maxlength="80"
          placeholder="Например, С питанием" /></label
      ><label
        >Описание<textarea
          v-model="form.description"
          rows="2"
          maxlength="400"
        ></textarea>
      </label>
      <div class="form-grid">
        <label
          >Доплата за гостя / ночь, ₸<input
            v-model.number="form.supplement"
            type="number"
            min="0"
            max="10000000"
            step="1"
            required /></label
        ><label
          >Статус<select v-model="form.status">
            <option value="active">Активен</option>
            <option value="disabled">Отключён</option>
          </select></label
        >
      </div>
      <label
        >Что включено, по одной услуге на строку<textarea
          v-model="form.features"
          rows="4"
          maxlength="400"
          placeholder="Трёхразовое питание&#10;Бассейн"
        ></textarea>
      </label>
      <p class="field-help">
        Итог = (цена номера + доплата × гости) × ночи. Сумма существующих броней
        не меняется.
      </p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          Отмена</button
        ><button class="primary" :disabled="busy">
          {{ busy ? "Сохраняем…" : "Сохранить тариф" }}
        </button>
      </div>
    </form></Modal
  >
</template>
