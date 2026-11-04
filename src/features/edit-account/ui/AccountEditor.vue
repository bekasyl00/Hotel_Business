<script setup>
import { useI18n } from "vue-i18n";
import { isDemo } from "@/shared/config";
import { reactive } from "vue";
import { Modal } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
const { t } = useI18n();
const props = defineProps({ item: Object, resorts: Array });
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  password: "",
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
    :title="item ? t('staff.configureAccess') : t('staff.newManager')"
    :busy="busy"
    @close="emit('close')"
    ><form
      class="editor-form"
      @submit.prevent="save({ ...form, password: form.password || undefined })"
    >
      <label
        >{{ t("staff.nameLabel")
        }}<input v-model="form.name" required maxlength="100" /></label
      ><label
        >{{ t("staff.login")
        }}<input
          v-model="form.login"
          required
          maxlength="100"
          placeholder="manager@demo.tynys"
          autocomplete="off" /></label
      ><label
        >{{ t("staff.resort")
        }}<select v-model="form.resortId" required>
          <option disabled value="">{{ t("staff.selectResort") }}</option>
          <option
            v-for="r in resorts.filter((r) => r.status !== 'archived')"
            :key="r.id"
            :value="r.id"
          >
            {{ r.name }}
          </option>
        </select></label
      ><label
        >{{ t("staff.access")
        }}<select v-model="form.status">
          <option value="active">{{ t("staff.active") }}</option>
          <option value="disabled">{{ t("staff.disabled") }}</option>
        </select></label
      >
      <label v-if="!isDemo"
        >{{ item ? t("staff.newPasswordOptional") : t("staff.initialPassword")
        }}<input
          v-model="form.password"
          type="password"
          :required="!item"
          minlength="12"
          maxlength="128"
          autocomplete="new-password"
      /></label>
      <p v-if="!isDemo" class="field-help">
        {{ t("staff.passwordHint") }}
      </p>
      <p v-if="isDemo" class="demo-note">
        {{ t("staff.demoAccountHint") }}
      </p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("staff.cancel") }}</button
        ><button class="primary" :disabled="busy">
          {{ busy ? t("staff.saving") : t("staff.saveAccess") }}
        </button>
      </div>
    </form></Modal
  >
</template>
