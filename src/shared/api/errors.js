import { getLocale, t } from "../i18n/index.js";
const codes = {
  invalid_credentials: "auth.invalidCredentials",
  phone_invalid: "auth.phoneInvalid",
  invalid_code: "auth.invalidCode",
  code_expired: "auth.expired",
  weak_password: "auth.weakPassword",
  sms_unavailable: "auth.unavailable",
  registration_failed: "auth.registrationFailed",
  phone_exists: "auth.registrationFailed",
  account_exists: "auth.registrationFailed",
  rate_limited: "common.error.rateLimit",
  resend_cooldown: "common.error.rateLimit",
  invalid_request: "common.error.validation",
  name_invalid: "common.error.validation",
  session_expired: "auth.sessionExpired",
  phone_change_requires_verification: "auth.phoneLocked",
};
export function errorMessage(message, status, code) {
  if (codes[code]) return t(codes[code]);
  if (getLocale() === "ru" && message) return message;
  const key =
    {
      401: "unauthorized",
      403: "forbidden",
      404: "notFound",
      409: "conflict",
      422: "validation",
      429: "rateLimit",
      502: "invalidResponse",
      503: "network",
    }[status] || "generic";
  return t(`common.error.${key}`);
}
