<script setup>
import { reactive } from "vue";
import { Modal } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
const props = defineProps({ item: Object, resorts: Array });
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  name: "",
  login: "",
  resortId: props.resorts[0]?.id || "",
  status: "active",
  ...props.item,
});
const { busy, error, save } = useEditor("accounts", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? 'Настроить доступ' : 'Новый управляющий'"
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save(form)">
      <label
        >Имя или обозначение<input
          v-model="form.name"
          required
          maxlength="100" /></label
      ><label
        >Логин<input
          v-model="form.login"
          required
          maxlength="100"
          placeholder="manager@demo.tynys"
          autocomplete="off" /></label
      ><label
        >Санаторий<select v-model="form.resortId" required>
          <option disabled value="">Выберите санаторий</option>
          <option
            v-for="r in resorts.filter((r) => r.status !== 'archived')"
            :key="r.id"
            :value="r.id"
          >
            {{ r.name }}
          </option>
        </select></label
      ><label
        >Доступ<select v-model="form.status">
          <option value="active">Активен</option>
          <option value="disabled">Отключён</option>
        </select></label
      >
      <p class="demo-note">
        Демо-аккаунт без пароля появится на экране входа. Он работает только в
        этом браузере. Серверные аккаунты подключим вместе с бэкендом.
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
          {{ busy ? "Сохраняем…" : "Сохранить доступ" }}
        </button>
      </div>
    </form></Modal
  >
</template>
