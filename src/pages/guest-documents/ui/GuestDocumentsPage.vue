<script setup>
import { useI18n } from "vue-i18n";
import { PublicHeader } from "@/widgets/public-header";
import { GuestDocuments } from "@/widgets/guest-documents";
const { t } = useI18n();
</script>

<template>
  <div class="public-site">
    <PublicHeader />
    <main id="public-main" class="profile-main documents-main">
      <RouterLink class="documents-back" to="/profile">
        <span aria-hidden="true">‹</span> {{ t("documents.backToProfile") }}
      </RouterLink>
      <header class="documents-heading">
        <h1>{{ t("documents.title") }}</h1>
      </header>
      <GuestDocuments />
    </main>
  </div>
</template>

<style scoped>
.documents-main {
  width: min(100% - 32px, 780px);
  margin-inline: auto;
  padding-block: 12px 28px;
}
.documents-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  color: var(--forest, #244e3e);
  font-size: 14px;
}
.documents-back span {
  font-size: 24px;
}
.documents-heading {
  margin-block: 6px 12px;
}
.documents-heading h1 {
  font-size: clamp(24px, 4vw, 30px);
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.025em;
}
</style>
