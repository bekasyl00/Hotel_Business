import { safeCheckoutUrl } from "./provider.js";

async function encodePng(url) {
  const { default: QRCode } = await import("qrcode");
  return QRCode.toDataURL(url, {
    type: "image/png",
    width: 256,
    margin: 4,
    errorCorrectionLevel: "M",
  });
}

export function createPaymentQrRenderer(
  onChange,
  { encode = encodePng, now = Date.now } = {},
) {
  let revision = 0;
  let disposed = false;
  const clear = () => onChange({ status: "idle", src: "" });
  return {
    async update({ provider, environment, url, expiresAt }) {
      if (disposed) return;
      const current = ++revision;
      clear();
      if (
        provider !== "xpayment" ||
        environment !== "production" ||
        !safeCheckoutUrl(provider, url, environment) ||
        !Number.isFinite(expiresAt) ||
        expiresAt <= now()
      )
        return;
      onChange({ status: "loading", src: "" });
      try {
        const src = await encode(url);
        if (disposed || current !== revision) return;
        if (expiresAt <= now()) {
          clear();
          return;
        }
        if (
          typeof src !== "string" ||
          !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(src)
        )
          throw new Error("Invalid local QR image");
        onChange({ status: "ready", src });
      } catch {
        if (!disposed && current === revision) {
          if (expiresAt <= now()) clear();
          else onChange({ status: "error", src: "" });
        }
      }
    },
    dispose() {
      disposed = true;
      revision++;
    },
  };
}
