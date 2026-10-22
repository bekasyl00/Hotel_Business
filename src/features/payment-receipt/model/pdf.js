import { i18n, getLocale } from "@/shared/i18n";
import { requestAsset } from "@/shared/api";
let fontPromise;
const clean = (value) =>
  String(value ?? "—")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .slice(0, 2000);
export async function generateDemoReceiptPdf(bundle, locale = getLocale()) {
  const t = (key, args = {}) =>
    i18n.global.t(`public.${key}`, args, { locale });
  const tag = { ru: "ru-KZ", kk: "kk-KZ", en: "en-GB" }[locale] || "ru-KZ";
  const receipt = bundle.receipt;
  const date = (value, timestamp = false) =>
    value
      ? new Intl.DateTimeFormat(tag, {
          day: "numeric",
          month: locale === "kk" ? "2-digit" : "short",
          year: "numeric",
          timeZone: timestamp ? receipt.timeZone || "Asia/Almaty" : "UTC",
          ...(timestamp
            ? {
                hour: "2-digit",
                minute: "2-digit",
                hourCycle: "h23",
                timeZoneName: "shortOffset",
              }
            : {}),
        }).format(new Date(value))
      : "—";

  const { jsPDF } = await import("jspdf");
  if (!fontPromise)
    fontPromise = requestAsset("/assets/fonts/NotoSans-Regular.ttf").catch(
      (error) => {
        fontPromise = null;
        throw error;
      },
    );
  const bytes = new Uint8Array(await fontPromise);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  const doc = new jsPDF({ unit: "mm", format: "a4", compress: true });
  doc.addFileToVFS("NotoSans-Regular.ttf", btoa(binary));
  doc.addFont("NotoSans-Regular.ttf", "NotoSans", "normal");
  doc.setFont("NotoSans", "normal");
  doc.setProperties({
    title: t("tynysDemoReceipt"),
    subject: t("notAKaspiReceipt"),
  });
  let top = 22;
  function paragraph(value, size = 10, color = [38, 57, 47]) {
    doc.setTextColor(...color);
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(clean(value), 170);
    for (const line of lines) {
      if (top > 275) {
        doc.addPage();
        top = 22;
      }
      doc.text(line, 20, top);
      top += size * 0.45 + 1.5;
    }
    top += 3;
  }
  const amount = (value) =>
    new Intl.NumberFormat(tag).format(value || 0) + " KZT";
  paragraph("Tynys", 24);
  paragraph(`${t("demoReceipt")} · ${t("notAKaspiReceipt")}`, 16);
  paragraph(
    t("noRealMoneyWasChargedThisPaymentWasSimulatedAnActualPaymentprovider"),
    10,
    [129, 74, 32],
  );
  if (receipt.legacySnapshot)
    paragraph(
      t("thisReceiptWasReconstructedFromAnOlderDemoSomeDetailsReflectWhen"),
      9,
      [99, 110, 102],
    );
  const row = (key, value) => paragraph(`${t(key)}: ${value}`);
  row("demoReceipt", receipt.number);
  row("dates", date(receipt.issuedAt, true));
  row("resort", receipt.resortName);
  row("location", receipt.resortAddress);
  row("guest", receipt.guestLabel);
  row("roomInReceiptPage", `${receipt.unit} · ${receipt.roomName}`);
  row("stayDates", `${date(receipt.start)} — ${date(receipt.end)}`);
  row("guestsNights", `${receipt.guests} / ${receipt.nights}`);
  row("checkinTimeInReceiptPage", date(receipt.checkinAt, true));
  row("rate", receipt.tariffName);
  if (receipt.discountPercent)
    row("discountInReceiptPage", `${receipt.discountPercent}%`);
  row("nightlyPrice", amount(receipt.nightly));
  paragraph(`${t("paidInDemo")}: ${amount(receipt.total)}`, 16);
  row("bookingReference", receipt.bookingId);
  row("payment", receipt.paymentId);
  if (bundle.refund) {
    top += 5;
    paragraph(t("demoRefund"), 14);
    paragraph(`${amount(bundle.refund.amount)} (${bundle.refund.percent}%)`);
    paragraph(
      bundle.refund.createdAt
        ? date(bundle.refund.createdAt, true)
        : t("theOldDemoDidNotRecordARefundDate"),
    );
  }
  paragraph(
    t("thisDocumentDoesNotConfirmARealPaymentAndIsNotAFiscal"),
    9,
    [99, 110, 102],
  );
  return doc.output("blob");
}
export function receiptFilename(number) {
  return `tynys-demo-${String(number || "receipt")
    .replace(/[^a-zA-Z0-9_-]/g, "_")
    .slice(0, 90)}.pdf`;
}
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
