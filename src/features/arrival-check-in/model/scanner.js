// Frames stay on this device. Only a decoded booking code goes to the API.
export async function createQrScanner(video, onCode, onError, deps = {}) {
  const media = deps.mediaDevices || navigator.mediaDevices;
  if (!media?.getUserMedia) throw new Error("camera_unavailable");
  let stopped = false,
    stream = null,
    timer = null;
  const stop = () => {
    stopped = true;
    clearTimeout(timer);
    stream?.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
  };
  const ready = (async () => {
    try {
      stream = await media.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
      });
      if (stopped) {
        stop();
        return;
      }
      video.srcObject = stream;
      await video.play();
      const decode = deps.decode || (await import("jsqr")).default;
      if (stopped) return;
      const canvas = deps.canvas || document.createElement("canvas");
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("camera_unavailable");
      const scan = () => {
        if (stopped) return;
        try {
          if (video.readyState >= 2 && video.videoWidth && video.videoHeight) {
            const scale = Math.min(1, 720 / video.videoWidth);
            canvas.width = Math.round(video.videoWidth * scale);
            canvas.height = Math.round(video.videoHeight * scale);
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            const pixels = context.getImageData(
              0,
              0,
              canvas.width,
              canvas.height,
            );
            const found = decode(pixels.data, pixels.width, pixels.height, {
              inversionAttempts: "attemptBoth",
            });
            if (found?.data) {
              stop();
              onCode(found.data);
              return;
            }
          }
          timer = setTimeout(scan, 150);
        } catch (error) {
          stop();
          onError(error);
        }
      };
      scan();
    } catch (error) {
      const cancelled = stopped;
      stop();
      if (!cancelled) onError(error);
    }
  })();
  return { stop, ready };
}
