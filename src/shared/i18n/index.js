import { createI18n } from "vue-i18n";
import ruCommon from "./locales/ru/common.json" with { type: "json" };
import kkCommon from "./locales/kk/common.json" with { type: "json" };
import enCommon from "./locales/en/common.json" with { type: "json" };
import ruAuth from "./locales/ru/auth.json" with { type: "json" };
import kkAuth from "./locales/kk/auth.json" with { type: "json" };
import enAuth from "./locales/en/auth.json" with { type: "json" };
import ruPublic from "./locales/ru/public.json" with { type: "json" };
import kkPublic from "./locales/kk/public.json" with { type: "json" };
import enPublic from "./locales/en/public.json" with { type: "json" };
import ruStaff from "./locales/ru/staff.json" with { type: "json" };
import kkStaff from "./locales/kk/staff.json" with { type: "json" };
import enStaff from "./locales/en/staff.json" with { type: "json" };

export const languages = [
  { value: "ru", label: "Русский" },
  { value: "kk", label: "Қазақша" },
  { value: "en", label: "English" },
];
const key = "tynys:locale:v1";
const valid = (value) => languages.some((language) => language.value === value);
function initialLocale() {
  try {
    const saved = globalThis.localStorage?.getItem(key);
    if (valid(saved)) return saved;
  } catch {}
  return "ru";
}
export const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: "ru",
  messages: {
    ru: { common: ruCommon, auth: ruAuth, public: ruPublic, staff: ruStaff },
    kk: { common: kkCommon, auth: kkAuth, public: kkPublic, staff: kkStaff },
    en: { common: enCommon, auth: enAuth, public: enPublic, staff: enStaff },
  },
});
export const t = (...args) => i18n.global.t(...args);
export const getLocale = () => i18n.global.locale.value;
export const localeTag = () =>
  ({ ru: "ru-KZ", kk: "kk-KZ", en: "en-GB" })[getLocale()];
export function setLocale(value) {
  if (!valid(value)) return false;
  i18n.global.locale.value = value;
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch {}
  syncDocumentLanguage();
  return true;
}
export function syncDocumentLanguage() {
  if (typeof document === "undefined") return;
  document.documentElement.lang = getLocale();
  document.title = t("common.appName");
}
