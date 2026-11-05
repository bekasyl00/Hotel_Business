export const isBankProvider = (provider) =>
  provider === "halyk_epay" || provider === "xpayment";

// Only provider checkout links are navigable, never arbitrary URLs from API data.
export function safeCheckoutUrl(provider, value) {
  if (typeof value !== "string" || value.length > 500 || value.trim() !== value)
    return null;
  const patterns = {
    halyk_epay:
      /^https:\/\/testepay\.homebank\.kz\/api\/redirect\/invoice-link\/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i,
    xpayment: /^https:\/\/qr\.kaspi\.kz\/[0-9]+$/,
  };
  return Object.hasOwn(patterns, provider) && patterns[provider].test(value)
    ? value
    : null;
}
