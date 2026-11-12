import type { CapacitorConfig } from "@capacitor/cli";

const variant = process.env.TYNYS_MOBILE_APP || "guest";
if (!["guest", "staff"].includes(variant))
  throw new Error("Unknown mobile app");
const staff = variant === "staff";
const config: CapacitorConfig = {
  appId: staff ? "kz.tynys.staff" : "kz.tynys.booking",
  appName: staff ? "Тыныс Команда" : "Тыныс",
  webDir: staff ? "dist/mobile-staff" : "dist/mobile",
  backgroundColor: "#f8f9f5",
  server: { errorPath: "native-update.html" },
  android: {
    path: staff ? "android-staff" : "android",
    allowMixedContent: false,
    webContentsDebuggingEnabled: false,
    minWebViewVersion: 107,
  },
  ios: {
    path: staff ? "ios-staff" : "ios",
    contentInset: "never",
    preferredContentMode: "mobile",
    scrollEnabled: true,
  },
  plugins: {
    CapacitorHttp: { enabled: true },
    ...(staff
      ? {
          PushNotifications: {
            presentationOptions: ["badge", "sound", "alert"],
          },
        }
      : {}),
  },
  includePlugins: staff
    ? [
        "@capacitor/filesystem",
        "@capacitor/share",
        "@capacitor/push-notifications",
      ]
    : ["@capacitor/filesystem", "@capacitor/share"],
  loggingBehavior: "none",
};
export default config;
