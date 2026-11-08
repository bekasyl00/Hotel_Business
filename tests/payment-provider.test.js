import test from "node:test";
import assert from "node:assert/strict";
import {
  isBankProvider,
  safeCheckoutUrl,
} from "../src/features/pay-booking/model/provider.js";

test("checkout URLs remain bound to their saved provider", () => {
  const halyk =
    "https://testepay.homebank.kz/api/redirect/invoice-link/49eb26c4-924a-4af5-a872-21b98b8c619e";
  const kaspi = "https://qr.kaspi.kz/55308082630746899169618031642188672381021";
  assert.equal(safeCheckoutUrl("halyk_epay", halyk), halyk);
  assert.equal(safeCheckoutUrl("xpayment", kaspi), kaspi);
  assert.equal(safeCheckoutUrl("halyk_epay", kaspi), null);
  assert.equal(safeCheckoutUrl("xpayment", halyk), null);
  assert.equal(safeCheckoutUrl("simulator", kaspi), null);
  assert.equal(safeCheckoutUrl("__proto__", kaspi), null);
  assert.equal(isBankProvider("xpayment"), true);
  assert.equal(isBankProvider("halyk_epay"), true);
  assert.equal(isBankProvider("kaspi-demo"), false);
});

test("Kaspi links reject URL tricks and extra destinations", () => {
  for (const value of [
    "http://qr.kaspi.kz/123",
    "https://qr.kaspi.kz.evil.test/123",
    "https://evil.test@qr.kaspi.kz/123",
    "https://qr.kaspi.kz@evil.test/123",
    "https://qr.kaspi.kz:443/123",
    "https://qr.kaspi.kz/123?redirect=https://evil.test",
    "https://qr.kaspi.kz/123#fragment",
    "https://qr.kaspi.kz/%31%32%33",
    "https://qr.kaspi.kz/123/../456",
    "https://qr.kaspi.kz/123\n",
    "javascript:alert(1)",
    "https://qr.kaspi.kz/",
    null,
    {},
  ])
    assert.equal(safeCheckoutUrl("xpayment", value), null, String(value));
});

test("XPayment sandbox URLs cannot navigate to a real checkout", () => {
  const sandbox = "https://xpayment.kz/sandbox/qr/123456789";
  assert.equal(safeCheckoutUrl("xpayment", sandbox, "sandbox"), sandbox);
  assert.equal(safeCheckoutUrl("xpayment", sandbox, "production"), null);
  assert.equal(
    safeCheckoutUrl("xpayment", "https://qr.kaspi.kz/123", "sandbox"),
    null,
  );
  for (const url of [
    sandbox + "?next=evil",
    sandbox + "#fragment",
    sandbox + "\n",
    "https://xpayment.kz.evil.test/sandbox/qr/123",
    "https://xpayment.kz:443/sandbox/qr/123",
    "https://xpayment.kz/app/sandbox",
  ])
    assert.equal(safeCheckoutUrl("xpayment", url, "sandbox"), null);
});
