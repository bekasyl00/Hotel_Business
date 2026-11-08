export const isBankProvider = (provider) =>
  provider === "halyk_epay" || provider === "xpayment";

export function bankCheckoutAccess(config, booking) {
  const hasExisting = isBankProvider(booking?.payment?.provider);
  const productionXPayment =
    config?.provider === "xpayment" && config.environment === "production";
  const resortUnavailable =
    productionXPayment &&
    (!Array.isArray(config.productionResortIds) ||
      typeof booking?.resortId !== "string" ||
      !config.productionResortIds.includes(booking.resortId));
  const environmentAllowed =
    config?.provider === "xpayment"
      ? ["sandbox", "production"].includes(config.environment)
      : config?.provider === "halyk_epay" && config.environment === "sandbox";
  const canCreate =
    config?.available === true && environmentAllowed && !resortUnavailable;
  return { canCreate, canView: hasExisting || canCreate, resortUnavailable };
}

// Only provider checkout links are navigable, never arbitrary URLs from API data.
export function safeCheckoutUrl(provider, value, environment = "production") {
  if (typeof value !== "string" || value.length > 500 || value.trim() !== value)
    return null;
  const patterns = {
    halyk_epay:
      /^https:\/\/testepay\.homebank\.kz\/api\/redirect\/invoice-link\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i,
    xpayment:
      environment === "sandbox"
        ? /^https:\/\/xpayment\.kz\/sandbox\/qr\/[0-9]+$/
        : /^https:\/\/qr\.kaspi\.kz\/[0-9]+$/,
  };
  return Object.hasOwn(patterns, provider) && patterns[provider].test(value)
    ? value
    : null;
}
