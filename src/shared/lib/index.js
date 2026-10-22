export const money = (value) =>
  new Intl.NumberFormat("ru-KZ").format(value || 0) + " ₸";
export const dateLabel = (value) =>
  value
    ? new Intl.DateTimeFormat("ru-KZ", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(value))
    : "—";
export const timeLabel = (value) =>
  new Intl.DateTimeFormat("ru-KZ", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Almaty",
  }).format(new Date(value));
export const asset = (name) => `/assets/${name}`;
export const categoryNames = {
  standard: "Стандарт",
  comfort: "Комфорт",
  suite: "Люкс",
};
export const statusNames = {
  published: "Опубликован",
  draft: "Черновик",
  archived: "В архиве",
  active: "Активен",
  maintenance: "На обслуживании",
  confirmed: "Подтверждена",
  cancelled: "Отменена",
  disabled: "Отключён",
};
