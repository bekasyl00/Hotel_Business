import { quoteStay } from "./rules.js";
import { shiftDay } from "./occupancy.js";

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

// Display estimates never change the underlying accommodation quote or snapshots.
export function customerPrice(resort, accommodationTotal) {
  if (!Number.isSafeInteger(accommodationTotal) || accommodationTotal < 0)
    return null;
  return paymentTerms(resort, accommodationTotal)?.total ?? accommodationTotal;
}

export function customerQuote(resort, quote) {
  if (!quote?.nightlyBreakdown?.length) return null;
  if (
    quote.nightlyBreakdown.some(
      (line) =>
        !Number.isSafeInteger(line.nightly) ||
        line.nightly < 0 ||
        !Number.isSafeInteger(line.regularNightly) ||
        line.regularNightly < 0,
    )
  )
    return null;
  let accommodationTotal = 0;
  let regularTotal = 0;
  let previousTotal = 0;
  let previousRegularTotal = 0;
  const nightlyBreakdown = quote.nightlyBreakdown.map((line) => {
    accommodationTotal += line.nightly;
    regularTotal += line.regularNightly;
    const total = customerPrice(resort, accommodationTotal);
    const regular = customerPrice(resort, regularTotal);
    const result = {
      date: line.date,
      periodLabel: line.periodLabel,
      nightly: total - previousTotal,
      regularNightly: regular - previousRegularTotal,
    };
    previousTotal = total;
    previousRegularTotal = regular;
    return result;
  });
  const uniform = (key) =>
    nightlyBreakdown.every((line) => line[key] === nightlyBreakdown[0][key])
      ? nightlyBreakdown[0][key]
      : null;
  return {
    total: previousTotal,
    regularTotal: previousRegularTotal,
    nights: nightlyBreakdown.length,
    nightly: uniform("nightly"),
    regularNightly: uniform("regularNightly"),
    averageNightly: Math.round(previousTotal / nightlyBreakdown.length),
    nightlyBreakdown,
  };
}

export function customerNightPrice(resort, room, tariff, search) {
  if (
    !room ||
    !/^\d{4}-\d{2}-\d{2}$/.test(search?.start || "") ||
    !Number.isFinite(Date.parse(search.start))
  )
    return null;
  const stay = { ...search, end: shiftDay(search.start, 1) };
  const current = quoteStay(room, tariff, stay);
  const ordinary = quoteStay({ ...room, pricePeriods: [] }, tariff, stay);
  if (!current || !ordinary) return null;
  const price = customerPrice(resort, current.total);
  const regularPrice = customerPrice(resort, ordinary.regularNightly);
  if (price == null || regularPrice == null) return null;
  return {
    date: search.start,
    price,
    regularPrice,
    kind:
      price < regularPrice
        ? "discount"
        : price > regularPrice
          ? "seasonal"
          : "regular",
  };
}
