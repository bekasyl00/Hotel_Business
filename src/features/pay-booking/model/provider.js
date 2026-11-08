export const isBankProvider = (provider) =>
  provider === "halyk_epay" || provider === "xpayment";

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
