import test from "node:test";
import assert from "node:assert/strict";
import QRCode from "qrcode";
import jsQR from "jsqr";
import { createQrScanner } from "../src/features/arrival-check-in/model/scanner.js";

test("ticket QR roundtrips locally without uploading camera frames", () => {
  const text =
    "TYNYS1.32721fa5-9b66-4515-bff7-5793b3defa5e:fictional-signature";
  const qr = QRCode.create(text, { errorCorrectionLevel: "M" }),
    scale = 6,
    margin = 4;
  const width = (qr.modules.size + margin * 2) * scale,
    pixels = new Uint8ClampedArray(width * width * 4).fill(255);
  for (let y = 0; y < qr.modules.size; y++)
    for (let x = 0; x < qr.modules.size; x++)
      if (qr.modules.get(y, x)) {
        for (let a = 0; a < scale; a++)
          for (let b = 0; b < scale; b++) {
            const i =
              (((y + margin) * scale + a) * width + (x + margin) * scale + b) *
              4;
            pixels[i] = pixels[i + 1] = pixels[i + 2] = 0;
          }
      }
  assert.equal(jsQR(pixels, width, width).data, text);
});

test("closing scanner before camera permission resolves stops eventual stream", async () => {
  let resolve,
    stopped = 0,
    played = 0;
  const video = {
    srcObject: null,
    play: () => {
      played++;
    },
  };
  const scanner = await createQrScanner(
    video,
    () => assert.fail(),
    () => assert.fail(),
    {
      mediaDevices: {
        getUserMedia: () =>
          new Promise((r) => {
            resolve = r;
          }),
      },
    },
  );
  scanner.stop();
  resolve({
    getTracks: () => [
      {
        stop: () => {
          stopped++;
        },
      },
    ],
  });
  await scanner.ready;
  assert.equal(stopped, 1);
  assert.equal(played, 0);
  assert.equal(video.srcObject, null);
});

test("decoded QR stops camera before delivering code and denied camera returns an error", async () => {
  let stopped = false,
    code;
  const video = {
    readyState: 4,
    videoWidth: 100,
    videoHeight: 100,
    play: async () => {},
  };
  const scanner = await createQrScanner(
    video,
    (value) => {
      assert.ok(stopped);
      code = value;
    },
    () => assert.fail(),
    {
      mediaDevices: {
        getUserMedia: async () => ({
          getTracks: () => [
            {
              stop: () => {
                stopped = true;
              },
            },
          ],
        }),
      },
      decode: () => ({ data: "ticket" }),
      canvas: {
        getContext: () => ({
          drawImage() {},
          getImageData: () => ({ data: [], width: 100, height: 100 }),
        }),
      },
    },
  );
  await scanner.ready;
  assert.equal(code, "ticket");
  assert.equal(video.srcObject, null);
  let error;
  const denied = await createQrScanner(
    video,
    () => assert.fail(),
    (e) => {
      error = e;
    },
    {
      mediaDevices: {
        getUserMedia: async () => {
          throw new Error("denied");
        },
      },
    },
  );
  await denied.ready;
  assert.equal(error.message, "denied");
});
