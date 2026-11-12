import { reactive, ref } from "vue";
import { Capacitor } from "@capacitor/core";

export const staffPushState = reactive({
  permission: "unknown",
  registeredDeviceId: null,
  registeredUserId: null,
  token: "",
  error: "",
});

export const pendingPushTarget = ref(null);

let pushPluginOverride = null;
let listenersBound = false;
let currentUser = null;
let currentRequest = null;
let actionHandler = null;

export function __setPushPluginForTests(plugin) {
  pushPluginOverride = plugin;
  listenersBound = false;
  currentUser = null;
  currentRequest = null;
  actionHandler = null;
  staffPushState.permission = "unknown";
  staffPushState.registeredDeviceId = null;
  staffPushState.registeredUserId = null;
  staffPushState.token = "";
  staffPushState.error = "";
  pendingPushTarget.value = null;
}

function activePlatform() {
  if (pushPluginOverride?.platform) return pushPluginOverride.platform;
  return Capacitor.getPlatform();
}

async function getPushPlugin() {
  if (pushPluginOverride) return pushPluginOverride;
  if (!Capacitor.isNativePlatform()) return null;
  const mod = await import("@capacitor/push-notifications");
  return mod.PushNotifications;
}

async function sendTokenToBackend(user, token, requestFn) {
  if (!user || user.role === "accountant" || !token || !requestFn) return;
  const platform = activePlatform();
  if (platform !== "ios" && platform !== "android") return;
  const res = await requestFn("POST", "/staff/push-devices", {
    platform,
    pushToken: token,
    appVersion: "1.1",
  });
  staffPushState.registeredDeviceId = res?.id || null;
  staffPushState.registeredUserId = user.id;
  staffPushState.error = "";
}

export async function initStaffPushListeners(onOpenTarget) {
  if (onOpenTarget) actionHandler = onOpenTarget;
  const plugin = await getPushPlugin();
  if (!plugin || listenersBound) return;
  listenersBound = true;

  if (
    activePlatform() === "android" &&
    typeof plugin.createChannel === "function"
  ) {
    await plugin
      .createChannel({
        id: "bookings",
        name: "Бронирования",
        description: "Системные уведомления о новых и оплаченных бронях",
        importance: 5,
        visibility: 1,
      })
      .catch(() => {});
  }

  await plugin.addListener("registration", async (tokenObj) => {
    const value = String(tokenObj?.value || "").trim();
    if (!value) return;
    staffPushState.token = value;
    if (currentUser && currentRequest) {
      try {
        await sendTokenToBackend(currentUser, value, currentRequest);
      } catch (e) {
        staffPushState.error = e?.message || "push_register_failed";
      }
    }
  });

  await plugin.addListener("registrationError", (err) => {
    staffPushState.error = String(
      err?.error || err?.message || "push_registration_error",
    );
  });

  await plugin.addListener("pushNotificationActionPerformed", (event) => {
    const data = event?.notification?.data || event?.data || {};
    const target = {
      bookingId: String(data.bookingId || "").trim(),
      resortId: String(data.resortId || "").trim(),
      notificationId: String(data.notificationId || "").trim(),
    };
    if (!target.bookingId && !target.notificationId) return;
    pendingPushTarget.value = target;
    actionHandler?.(target);
  });
}

export async function revokeStaffPushDevice(requestFn = currentRequest) {
  const req = requestFn || currentRequest;
  const idOrToken = staffPushState.registeredDeviceId || staffPushState.token;
  staffPushState.registeredDeviceId = null;
  staffPushState.registeredUserId = null;
  currentUser = null;
  if (req && idOrToken) {
    await req(
      "DELETE",
      `/staff/push-devices/${encodeURIComponent(idOrToken)}`,
    ).catch(() => {});
  }
}

export async function syncStaffPushSession(user, requestFn, onOpenTarget) {
  if (requestFn) currentRequest = requestFn;
  if (onOpenTarget) actionHandler = onOpenTarget;
  const plugin = await getPushPlugin();
  if (!plugin) return;

  await initStaffPushListeners(onOpenTarget);

  if (!user || user.role === "accountant") {
    if (staffPushState.registeredDeviceId || staffPushState.registeredUserId) {
      await revokeStaffPushDevice(currentRequest);
    }
    currentUser = null;
    return;
  }

  if (
    staffPushState.registeredUserId &&
    staffPushState.registeredUserId !== user.id
  ) {
    staffPushState.registeredDeviceId = null;
    staffPushState.registeredUserId = null;
  }

  currentUser = user;

  try {
    let perm = await plugin.checkPermissions();
    if (
      perm?.receive === "prompt" ||
      perm?.receive === "prompt-with-rationale"
    ) {
      perm = await plugin.requestPermissions();
    }
    staffPushState.permission = perm?.receive || "unknown";
  } catch (e) {
    staffPushState.permission = "unavailable";
    staffPushState.error = e?.message || "push_permission_failed";
    return;
  }

  if (staffPushState.permission !== "granted") return;

  const tokenBeforeRegister = staffPushState.token;
  try {
    await plugin.register();
  } catch (e) {
    staffPushState.error = e?.message || "push_register_failed";
    return;
  }

  if (
    staffPushState.token &&
    staffPushState.token === tokenBeforeRegister &&
    staffPushState.registeredUserId !== user.id
  ) {
    try {
      await sendTokenToBackend(user, staffPushState.token, currentRequest);
    } catch (e) {
      staffPushState.error = e?.message || "push_register_failed";
    }
  }
}

export function consumePendingPushTarget() {
  const target = pendingPushTarget.value;
  pendingPushTarget.value = null;
  return target;
}
