import test from "node:test";
import assert from "node:assert/strict";
import {
  csvCell,
  comparison,
  reportDateAfter,
} from "../src/pages/analytics/model/format.js";
test("analytics CSV neutralises formulas including whitespace-prefixed names", () => {
  for (const value of [
    "=1+1",
    "+SUM(A1)",
    "-cmd",
    "@formula",
    "   =1+1",
    "\tname",
    "\rname",
    "\nname",
  ])
    assert.ok(csvCell(value).startsWith("\"'"));
  assert.equal(csvCell(-12), '"-12"');
  assert.equal(csvCell('Санаторий "Тыныс"'), '"Санаторий ""Тыныс"""');
});
test("analytics comparison distinguishes zero baseline and signed cashflow", () => {
  assert.equal(comparison(0, 0), "Без изменений");
  assert.equal(comparison(10, 0), "Нет базы для сравнения");
  assert.equal(comparison(0, 20), "-100%");
  assert.equal(comparison(-10, -20), "+50%");
});

test("analytics period follows Almaty midnight across month boundaries", () => {
  assert.equal(
    reportDateAfter(0, new Date("2026-10-22T19:01:00Z")),
    "2026-10-23",
  );
  assert.equal(
    reportDateAfter(-27, new Date("2026-10-22T19:01:00Z")),
    "2026-09-26",
  );
  assert.equal(
    reportDateAfter(-1, new Date("2026-03-31T20:00:00Z")),
    "2026-03-31",
  );
});
