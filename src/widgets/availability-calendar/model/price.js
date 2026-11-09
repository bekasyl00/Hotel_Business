export function calendarDayPrice(day) {
  if (
    !day?.bookable ||
    !Number.isInteger(day.availableRooms) ||
    day.availableRooms <= 0 ||
    !Number.isSafeInteger(day.price) ||
    day.price < 0
  )
    return null;
  const regular =
    Number.isSafeInteger(day.regularPrice) && day.regularPrice >= 0
      ? day.regularPrice
      : day.price;
  const kind = !day.hasPricePeriod
    ? "regular"
    : day.price < regular
      ? "discount"
      : "seasonal";
  return {
    amount: day.price,
    regular,
    kind,
    periodLabel: day.periodLabel || "",
  };
}

export function compactCalendarPrice(amount, locale) {
  if (!Number.isSafeInteger(amount) || amount < 0) return "";
  const scale = amount >= 999950 ? 1000000 : amount >= 1000 ? 1000 : 1;
  const value = new Intl.NumberFormat(locale, {
    useGrouping: false,
    maximumFractionDigits: scale === 1 ? 0 : 1,
  }).format(amount / scale);
  return `${value}${scale === 1000000 ? "M" : scale === 1000 ? "K" : ""}`;
}
