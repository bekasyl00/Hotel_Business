import test from "node:test";
import assert from "node:assert/strict";
import { holdSeconds, holdLabel } from "../src/entities/booking/model/hold.js";
test("payment countdown uses the frozen deadline and never restarts on reload", () => {
  const start = Date.parse("2030-01-01T08:00:00Z"),
    expires = "2030-01-01T08:15:00Z";
  assert.equal(holdLabel(holdSeconds(expires, start)), "15:00");
  assert.equal(holdLabel(holdSeconds(expires, start + 60000)), "14:00");
  assert.equal(holdLabel(holdSeconds(expires, start + 899999)), "00:01");
  assert.equal(holdSeconds(expires, start + 900000), 0);
  assert.equal(holdSeconds(expires, start + 999999), 0);
  assert.equal(holdSeconds(null, start), null);
});
