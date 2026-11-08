import test from "node:test";
import assert from "node:assert/strict";
import {
  canOpenVoucher,
  canRecordOnsite,
} from "../src/features/booking-voucher/model/access.js";

test("voucher is offered only after a confirmed booking has a successful payment", () => {
  assert.equal(
    canOpenVoucher({
      status: "pending",
      payment: { checkoutStatus: "succeeded" },
    }),
    false,
  );
  assert.equal(
    canOpenVoucher({
      status: "cancelled",
      payment: { checkoutStatus: "succeeded" },
    }),
    false,
  );
  assert.equal(
    canOpenVoucher({
      status: "confirmed",
      payment: { checkoutStatus: "pending" },
    }),
    false,
  );
  assert.equal(
    canOpenVoucher({
      status: "confirmed",
      payment: { checkoutStatus: "succeeded" },
    }),
    true,
  );
  assert.equal(
    canOpenVoucher({ status: "confirmed", payment: { status: "paid" } }),
    true,
  );
});

test("on-site collection controls respect role, stay dates, collection and check-out state", () => {
  const voucher = {
    status: "confirmed",
    start: "2026-11-08",
    end: "2026-11-10",
    paymentTerms: { onsiteAmount: 10000 },
    onsitePayment: { status: "due" },
  };
  assert.equal(canRecordOnsite(voucher, {}, "2026-11-08", true), true);
  assert.equal(canRecordOnsite(voucher, {}, "2026-11-07", true), false);
  assert.equal(canRecordOnsite(voucher, {}, "2026-11-10", true), false);
  assert.equal(canRecordOnsite(voucher, {}, "2026-11-09", false), false);
  assert.equal(
    canRecordOnsite(voucher, { stayStatus: "checked_out" }, "2026-11-09", true),
    false,
  );
  assert.equal(
    canRecordOnsite(
      { ...voucher, onsitePayment: { status: "recorded" } },
      {},
      "2026-11-09",
      true,
    ),
    false,
  );
  assert.equal(
    canRecordOnsite(
      { ...voucher, paymentTerms: { onsiteAmount: 0 } },
      {},
      "2026-11-09",
      true,
    ),
    false,
  );
});
