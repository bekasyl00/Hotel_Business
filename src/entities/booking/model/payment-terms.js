// Estimate only; the server freezes authoritative terms when booking is created.
export function paymentTerms(resort, total) {
  if (!Number.isSafeInteger(total) || total < 0) return null;
  const value = Number(resort?.bookingFeePercent ?? resort?.commissionPercent);
  if (!Number.isFinite(value) || value <= 0 || value > 100) return null;
  const units = Math.round(value * 100);
  const onlineAmount = Math.floor((total * units + 5000) / 10000);
  if (onlineAmount < 1) return null;
  return {
    version: 1,
    total: total + onlineAmount,
    accommodationTotal: total,
    mode: "percent",
    value: String(value),
    onlineAmount,
    onsiteAmount: total,
  };
}
