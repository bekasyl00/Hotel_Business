import test from "node:test";
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { baseCompile } from "@intlify/message-compiler";
import { i18n, setLocale, getLocale, t } from "../src/shared/i18n/index.js";
import {
  dateLabel,
  categoryNames,
  statusNames,
} from "../src/shared/lib/index.js";
import { validateSearch } from "../src/entities/booking/rules.js";
function flatten(value, prefix = "") {
  return Object.fromEntries(
    Object.entries(value).flatMap(([k, v]) =>
      typeof v === "string"
        ? [[prefix + k, v]]
        : Object.entries(flatten(v, prefix + k + ".")),
    ),
  );
}
const messages = Object.fromEntries(
  ["ru", "kk", "en"].map((l) => [l, flatten(i18n.global.getLocaleMessage(l))]),
);
test("all locales contain the same keys and interpolation parameters; every message compiles", () => {
  for (const locale of ["ru", "kk", "en"]) {
    assert.deepEqual(
      Object.keys(messages[locale]).sort(),
      Object.keys(messages.ru).sort(),
    );
    for (const [key, value] of Object.entries(messages[locale])) {
      assert.ok(value.trim(), `${locale}:${key}`);
      const params = (s) =>
        [...s.matchAll(/\{([A-Za-z0-9][\w]*)\}/g)].map((m) => m[1]).sort();
      assert.deepEqual(
        params(value),
        params(messages.ru[key]),
        `${locale}:${key}`,
      );
      baseCompile(value, {
        onError: (e) => assert.fail(`${locale}:${key} ${e.message}`),
      });
    }
  }
});
test("literal translation references resolve instead of showing raw keys", async () => {
  async function walk(dir) {
    const entries = await readdir(dir, { withFileTypes: true });
    return (
      await Promise.all(
        entries.map((e) =>
          e.isDirectory()
            ? walk(`${dir}/${e.name}`)
            : /\.(js|vue)$/.test(e.name)
              ? [`${dir}/${e.name}`]
              : [],
        ),
      )
    ).flat();
  }
  for (const file of await walk("src")) {
    const text = await readFile(file, "utf8");
    for (const m of text.matchAll(
      /\bt\(\s*['"]((?:auth|common|public|staff)\.[\w.]+)['"]/g,
    ))
      assert.ok(messages.ru[m[1]], `${file}: ${m[1]}`);
  }
});
test("locale changes update validation, statuses and dates without changing booking data", () => {
  try {
    setLocale("en");
    assert.equal(getLocale(), "en");
    assert.equal(categoryNames.suite, "Suite");
    assert.equal(statusNames.pending, t("common.status.pending"));
    assert.match(
      validateSearch(
        { start: "2030-01-02", end: "2030-01-01", guests: 1 },
        "2030-01-01",
      ),
      /Check-out/,
    );
    setLocale("kk");
    assert.doesNotMatch(dateLabel("2030-10-23"), /M10/);
    assert.equal(setLocale("de"), false);
    assert.equal(getLocale(), "kk");
    setLocale("ru");
    assert.equal(categoryNames.suite, "Люкс");
  } finally {
    setLocale("ru");
  }
});
