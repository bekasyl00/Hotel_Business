import test from "node:test";
import assert from "node:assert/strict";
import {
  checkoutAmounts,
  paymentNeedsPolling,
  paymentStage,
} from "../src/features/pay-booking/model/presentation.js";

test("checkout separates a frozen online fee from the amount payable at property", () => {
  const booking = {
    total: 270000,
    paymentTerms: {
      version: 1,
      total: 280000,
      onlineAmount: 10000,
      onsiteAmount: 270000,
    },
  };
  assert.deepEqual(checkoutAmounts(booking), {
    total: 280000,
    online: 10000,
    onsite: 270000,
  });
  assert.deepEqual(checkoutAmounts(booking, { amount: 280000 }), {
    total: 280000,
    online: 280000,
    onsite: 0,
  });
  assert.equal(
    checkoutAmounts({ ...booking, payment: { amount: 280000 } }).online,
    280000,
  );
  assert.equal(checkoutAmounts({ total: 30000 }).online, 30000);
  assert.equal(
    checkoutAmounts({
      ...booking,
      paymentTerms: { ...booking.paymentTerms, onsiteAmount: 280000 },
    }).online,
    270000,
  );
});

test("a successful charge continues polling until its queued refund is verified", () => {
  for (const refundStatus of ["queued", "submitted"])
    assert.equal(
      paymentNeedsPolling({ status: "succeeded", refundStatus }),
      true,
    );
  for (const refundStatus of ["succeeded", "reconciliation_required"])
    assert.equal(
      paymentNeedsPolling({ status: "succeeded", refundStatus }),
      false,
    );
  assert.equal(paymentNeedsPolling({ checkoutStatus: "pending" }), true);
  assert.equal(paymentNeedsPolling({ status: "expired" }), false);
  assert.equal(paymentNeedsPolling(null), false);
});

test("opening a bank link only changes the waiting stage, never marks a payment successful", () => {
  const pending = { status: "pending" };
  assert.equal(paymentStage(pending, { hasLink: true }), "ready");
  assert.equal(
    paymentStage(pending, { hasLink: true, opened: true }),
    "verifying",
  );
  assert.equal(paymentStage({ status: "creating" }), "creating");
  assert.equal(
    paymentStage({ status: "succeeded", refundStatus: "submitted" }),
    "refund_submitted",
  );
  assert.equal(paymentStage({ status: "succeeded" }), "succeeded");
});
