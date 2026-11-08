const amount = (value) => Number.isSafeInteger(value) && value >= 0;

export function checkoutAmounts(booking, payment = null) {
  const terms = booking?.paymentTerms;
  const legacyTotal = amount(booking?.total) ? booking.total : 0;
  const savedAmount = payment?.amount ?? booking?.payment?.amount;
  const validTerms =
    terms?.version === 1 &&
    amount(terms.total) &&
    amount(terms.onlineAmount) &&
    amount(terms.onsiteAmount) &&
    terms.onlineAmount + terms.onsiteAmount === terms.total;
  const total = validTerms ? terms.total : legacyTotal;
  const online = amount(savedAmount)
    ? savedAmount
    : validTerms
      ? terms.onlineAmount
      : total;
  return { total, online, onsite: Math.max(0, total - online) };
}

export function paymentNeedsPolling(payment) {
  if (!payment) return false;
  if (["queued", "submitted"].includes(payment.refundStatus)) return true;
  return ["creating", "pending", "failed"].includes(
    payment.status || payment.checkoutStatus,
  );
}

export function paymentStage(
  payment,
  { hasLink = false, opened = false } = {},
) {
  if (payment?.refundStatus) return `refund_${payment.refundStatus}`;
  if (
    ["expired", "failed", "reconciliation_required"].includes(payment?.status)
  )
    return payment.status;
  if (payment?.status === "succeeded") return "succeeded";
  if (payment?.status === "creating") return "creating";
  if (payment?.status === "pending")
    return hasLink && !opened ? "ready" : "verifying";
  return payment ? "loading" : "initial";
}
