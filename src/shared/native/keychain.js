import { Capacitor, registerPlugin } from "@capacitor/core";

export const isNative = () => Capacitor.isNativePlatform();
export const nativePlatform = () => Capacitor.getPlatform();
export const keychainPlugin = registerPlugin("TynysKeychain");

export async function isNativePushAvailable() {
  if (!isNative()) return false;
  if (typeof keychainPlugin.pushAvailable !== "function") return true;
  try {
    const res = await Promise.race([
      keychainPlugin.pushAvailable(),
      new Promise((resolve) =>
        setTimeout(() => resolve({ available: true }), 1500),
      ),
    ]);
    return res?.available !== false;
  } catch {
    return false;
  }
}
