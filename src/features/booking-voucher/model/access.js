export function canOpenVoucher(booking) {
  return (
    booking?.status === "confirmed" &&
    (booking.payment?.checkoutStatus === "succeeded" ||
      booking.payment?.status === "paid")
  );
}

export function canRecordOnsite(voucher, booking, today, allowed) {
  return (
    allowed === true &&
    voucher?.status === "confirmed" &&
    voucher.onsitePayment?.status !== "recorded" &&
    Number.isSafeInteger(voucher.paymentTerms?.onsiteAmount) &&
    voucher.paymentTerms.onsiteAmount > 0 &&
    today >= voucher.start &&
    today < voucher.end &&
    !booking?.checkedOutAt &&
    booking?.stayStatus !== "checked_out"
  );
}
