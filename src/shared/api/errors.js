import { getLocale, t } from "../i18n/index.js";
const codes = {
  invalid_token: "auth.sessionExpired",
  native_web_auth_required: "common.mobile.webAuth",
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
  media_invalid: "common.media.invalid",
  media_image_required: "common.media.imageRequired",
  media_image_size: "common.media.imageSize",
  media_video_size: "common.media.videoSize",
  media_storage_unavailable: "common.media.storageUnavailable",
  media_quota: "common.media.quota",
  media_avatar_account: "common.media.avatarAccount",
  media_not_found: "common.media.notFound",
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
