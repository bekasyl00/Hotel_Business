import test from "node:test";
import assert from "node:assert/strict";
import { createPaymentQrRenderer } from "../src/features/pay-booking/model/qr.js";

const input = {
  provider: "xpayment",
  environment: "production",
  url: "https://qr.kaspi.kz/123456789",
  expiresAt: 2000,
};
const png = "data:image/png;base64,aGVsbG8=";
const otherPng = "data:image/png;base64,d29ybGQ=";
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test("QR never encodes other providers, sandbox, unsafe links or expired attempts", async () => {
  let encoded = 0,
    state;
  const renderer = createPaymentQrRenderer(
    (value) => {
      state = value;
    },
    {
      now: () => 1000,
      encode: async () => {
        encoded++;
        return png;
      },
    },
  );
  for (const changes of [
    { provider: "halyk_epay" },
    { environment: "sandbox", url: "https://xpayment.kz/sandbox/qr/123" },
    { environment: "live" },
    { url: "https://qr.kaspi.kz.evil.test/123" },
    { url: input.url + "?redirect=elsewhere" },
    { url: null },
    { expiresAt: 1000 },
    { expiresAt: NaN },
  ]) {
    await renderer.update({ ...input, ...changes });
    assert.deepEqual(state, { status: "idle", src: "" });
  }
  assert.equal(encoded, 0);
});

test("a changed checkout clears the previous QR and ignores late results", async () => {
  const a = deferred(),
    b = deferred(),
    inputs = [];
  let state;
  const renderer = createPaymentQrRenderer(
    (value) => {
      state = value;
    },
    {
      now: () => 1000,
      encode: (url) => {
        inputs.push(url);
        return inputs.length === 1 ? a.promise : b.promise;
      },
    },
  );
  const first = renderer.update(input);
  const second = renderer.update({
    ...input,
    url: "https://qr.kaspi.kz/987654321",
  });
  assert.deepEqual(state, { status: "loading", src: "" });
  b.resolve(otherPng);
  await second;
  a.resolve(png);
  await first;
  assert.deepEqual(inputs, [input.url, "https://qr.kaspi.kz/987654321"]);
  assert.deepEqual(state, { status: "ready", src: otherPng });
  await renderer.update({ ...input, url: null });
  assert.deepEqual(state, { status: "idle", src: "" });
});

test("expiry or component disposal cannot publish an in-flight QR", async () => {
  for (const action of ["expire", "clear", "dispose"]) {
    const work = deferred();
    let clock = 1000,
      state;
    const renderer = createPaymentQrRenderer(
      (value) => {
        state = value;
      },
      {
        now: () => clock,
        encode: () => work.promise,
      },
    );
    const pending = renderer.update(input);
    if (action === "expire") clock = input.expiresAt;
    if (action === "clear") await renderer.update({ ...input, url: null });
    if (action === "dispose") renderer.dispose();
    work.resolve(png);
    await pending;
    assert.equal(state.src, "", action);
    assert.notEqual(state.status, "ready", action);
  }
});

test("local QR failures are visible and never replaced by remote image URLs", async () => {
  for (const encode of [
    async () => {
      throw new Error("Renderer failed");
    },
    async () => "https://external-qr.example/image.png",
  ]) {
    let state;
    const renderer = createPaymentQrRenderer(
      (value) => {
        state = value;
      },
      { now: () => 1000, encode },
    );
    await renderer.update(input);
    assert.deepEqual(state, { status: "error", src: "" });
    assert.equal(input.url, "https://qr.kaspi.kz/123456789");
  }
});

test("real local encoder produces PNG bytes without an image service", async () => {
  let state;
  const renderer = createPaymentQrRenderer(
    (value) => {
      state = value;
    },
    { now: () => 1000 },
  );
  await renderer.update(input);
  assert.equal(state.status, "ready");
  const bytes = Buffer.from(state.src.split(",")[1], "base64");
  assert.deepEqual(
    bytes.subarray(0, 8),
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  );
  assert.equal(bytes.readUInt32BE(16), 256);
  assert.equal(bytes.readUInt32BE(20), 256);
});
