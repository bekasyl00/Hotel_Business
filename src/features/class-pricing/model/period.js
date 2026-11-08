export function classPricingConflicts(rooms, period) {
  if (!period.start || !period.end || period.end <= period.start) return [];
  return rooms.filter(
    (room) =>
      (room.pricePeriods || []).length >= 60 ||
      (room.pricePeriods || []).some(
        (saved) => saved.start < period.end && period.start < saved.end,
      ),
  );
}

export function classPricingPayload(preview, period) {
  const price = Number(period.price);
  if (
    !preview?.rooms?.length ||
    !period.label.trim() ||
    !period.start ||
    !period.end ||
    period.end <= period.start ||
    period.price === "" ||
    !Number.isInteger(price) ||
    price < 0 ||
    price > 10000000
  )
    return null;
  return {
    resortVersion: preview.resortVersion,
    category: preview.category,
    rooms: preview.rooms.map(({ id, version }) => ({ id, version })),
    period: {
      label: period.label.trim(),
      start: period.start,
      end: period.end,
      price,
    },
  };
}
