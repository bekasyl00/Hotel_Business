import {
  isNative,
  nativePlatform,
  keychainPlugin,
  isNativePushAvailable,
} from "./keychain.js";

export { isNative, nativePlatform, isNativePushAvailable };
export const nativeVault = {
  async read() {
    const { value } = await keychainPlugin.read();
    return value ? JSON.parse(value) : null;
  },
  write: (value) => keychainPlugin.write({ value: JSON.stringify(value) }),
  clear: () => keychainPlugin.clear(),
};

export async function openSystemNotificationSettings() {
  if (!isNative() || typeof keychainPlugin.openSettings !== "function") return;
  await keychainPlugin.openSettings().catch(() => {});
}

export async function shareNativeFile(file, title) {
  const [{ Filesystem, Directory }, { Share }] = await Promise.all([
    import("@capacitor/filesystem"),
    import("@capacitor/share"),
  ]);
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  const path = `receipts/${crypto.randomUUID()}.pdf`;
  const result = await Filesystem.writeFile({
    path,
    data: btoa(binary),
    directory: Directory.Cache,
    recursive: true,
  });
  try {
    await Share.share({ title, files: [result.uri], dialogTitle: title });
  } finally {
    await Filesystem.deleteFile({ path, directory: Directory.Cache }).catch(
      () => {},
    );
  }
}

export async function clearReceiptCache() {
  const { Filesystem, Directory } = await import("@capacitor/filesystem");
  await Filesystem.rmdir({
    path: "receipts",
    directory: Directory.Cache,
    recursive: true,
  }).catch(() => {});
}

export { nativeSessionNotice } from "./status.js";
export {
  staffPushState,
  pendingPushTarget,
  initStaffPushListeners,
  syncStaffPushSession,
  revokeStaffPushDevice,
  consumePendingPushTarget,
  __setPushPluginForTests,
} from "./push.js";
