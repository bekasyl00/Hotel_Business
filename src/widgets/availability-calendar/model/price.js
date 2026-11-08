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
