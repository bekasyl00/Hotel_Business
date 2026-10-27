import test from "node:test";
import assert from "node:assert/strict";
import { timestampLabel, dateLabel } from "../src/shared/lib/index.js";
import { freezeDemoReceipt } from "../src/app/providers/demo-guests.js";

test("receipt timestamps cross Almaty midnight while stay dates remain date-only", () => {
  const before = timestampLabel("2026-10-22T18:59:00Z");
  const after = timestampLabel("2026-10-22T19:22:00Z", "Asia/Almaty");
  assert.match(before, /22 окт.*2026.*23:59/);
  assert.match(after, /23 окт.*2026.*00:22/);
  assert.match(after, /GMT\+5/);
  assert.match(timestampLabel("2026-12-31T19:00:00Z"), /1 янв.*2027.*00:00/);
  assert.match(dateLabel("2026-10-22"), /22 окт.*2026/);
  assert.match(
    timestampLabel("2026-10-22T19:22:00Z", "UTC"),
    /22 окт.*2026.*19:22/,
  );
  assert.match(
    timestampLabel("2026-10-29T14:00:00+05:00", "Asia/Almaty"),
    /29 окт.*2026.*14:00/,
  );
  assert.equal(timestampLabel(null), "—");
  assert.equal(timestampLabel("not-a-date"), "—");
  assert.equal(timestampLabel("2026-10-22T19:22:00Z", "invalid"), after);
});

test("demo receipt freezes booking timezone rather than current resort settings", () => {
  const db = { resorts: [{ id: "resort", timeZone: "UTC" }] };
  const booking = {
    id: "booking",
    resortId: "resort",
    cancellationPolicy: {
      timeZone: "Asia/Almaty",
      checkinAt: "2026-10-29T14:00:00+05:00",
    },
  };
  const receipt = freezeDemoReceipt(db, booking, {
    id: "payment",
    createdAt: "2026-10-22T19:22:00Z",
    amount: 100,
  });
  assert.equal(receipt.timeZone, "Asia/Almaty");
  booking.cancellationPolicy.timeZone = "UTC";
  assert.equal(receipt.timeZone, "Asia/Almaty");
  assert.match(
    timestampLabel(receipt.issuedAt, receipt.timeZone),
    /23 окт.*2026.*00:22/,
  );
  assert.equal(
    freezeDemoReceipt({ resorts: [] }, { id: "legacy" }, { id: "payment" })
      .timeZone,
    "Asia/Almaty",
  );
});
