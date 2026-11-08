import { ApiError } from "../../shared/api/index.js";
const fail = (message, status = 422) => {
  throw new ApiError(message, status);
};
const profile = (user) => ({
  id: user.id,
  version: user.profileVersion || 1,
  accountVersion: user.version || 1,
  name: user.name,
  jobTitle: user.jobTitle || "",
  contactPhone: user.contactPhone || "",
  login: user.login,
  role: user.role,
});
export function demoStaffProfile({
  db,
  user,
  method,
  pathname,
  payload,
  commit,
}) {
  if (pathname !== "/staff-profile") return { handled: false };
  if (!user) fail("Войдите в кабинет сотрудника.", 401);
  if (method === "GET")
    return {
      handled: true,
      value: {
        profile: profile(user),
        resorts: db.resorts
          .filter(
            (r) =>
              ["admin", "accountant"].includes(user.role) ||
              r.accountId === user.id,
          )
          .map(({ id, name }) => ({ id, name })),
      },
    };
  if (method !== "PATCH") fail("Метод недоступен.", 405);
  const allowed = [
    "name",
    "jobTitle",
    "contactPhone",
    "version",
    "accountVersion",
  ];
  if (
    !payload ||
    typeof payload !== "object" ||
    Array.isArray(payload) ||
    Object.keys(payload).some((k) => !allowed.includes(k))
  )
    fail("Неизвестные поля профиля.");
  if (
    payload.version !== (user.profileVersion || 1) ||
    payload.accountVersion !== (user.version || 1)
  )
    fail("Профиль уже изменён. Обновите страницу.", 409);
  for (const key of ["name", "jobTitle", "contactPhone"])
    if (
      typeof payload[key] !== "string" ||
      payload[key].trim().length > (key === "contactPhone" ? 30 : 100)
    )
      fail("Проверьте поля профиля.");
  if (!payload.name.trim()) fail("Укажите имя.");
  const phone = payload.contactPhone
    .trim()
    .replace(/[ ()-]/g, "")
    .replace(/^\+?/, "");
  if (phone && !/^[1-9][0-9]{6,14}$/.test(phone))
    fail("Укажите рабочий телефон с кодом страны.");
  const before = { id: user.id, version: user.profileVersion || 1 };
  user.name = payload.name.trim();
  user.jobTitle = payload.jobTitle.trim();
  user.contactPhone = phone ? "+" + phone : "";
  user.profileVersion = (user.profileVersion || 1) + 1;
  commit(
    "staffProfile",
    { id: user.id, version: user.profileVersion },
    before,
    "update",
  );
  return { handled: true, value: { profile: profile(user), account: user } };
}
