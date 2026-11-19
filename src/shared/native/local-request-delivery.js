// Foreground request delivery; no Firebase, APNs or remote push.
import { Capacitor } from '@capacitor/core';
let android;
let activeAccount = '';
let onOpen;
let pendingTap;
let queue = Promise.resolve();
const displayed = new Map();
const androidAccountKey = 'tynys:local-notification-account';
const key = (account) => `tynys:request-notices:${account}`;
const ids = (account) => { try { return new Set(JSON.parse(localStorage.getItem(key(account)) || '[]')); } catch { return new Set(); } };
const save = (account, seen) => localStorage.setItem(key(account), JSON.stringify([...seen]));

async function plugin() {
  if (!android) {
    android = (await import('@capacitor/local-notifications')).LocalNotifications;
    await android.createChannel({ id: 'requests', name: 'Запросы', importance: 5, vibration: true }).catch(() => {}); // Android <26 has no channels.
    await android.addListener('localNotificationActionPerformed', ({ notification }) => {
      const extra = notification.extra;
      if (!extra?.account) return;
      if (!activeAccount) pendingTap = extra;
      else if (extra.account === activeAccount) onOpen?.(extra.target);
    });
  }
  return android;
}

export async function requestDeliveryPermission() {
  if (Capacitor.getPlatform() === 'android') return (await (await plugin()).requestPermissions()).display;
  if (typeof Notification === 'undefined') return 'unsupported';
  return Notification.requestPermission();
}

export function deliverLocalRequests(account, items, open) {
  queue = queue.catch(() => {}).then(() => {
    const run = async () => {
    onOpen = open;
    const native = Capacitor.getPlatform() === 'android';
    const api = native ? await plugin() : null;
    if (account !== activeAccount) {
      for (const notice of displayed.values()) notice.close();
      displayed.clear();
      activeAccount = account;
    }
    if (api && (localStorage.getItem(androidAccountKey) || '') !== account) {
      await api.cancel(await api.getPending());
      await api.removeAllDeliveredNotifications();
      localStorage.setItem(androidAccountKey, account);
    }
    const permission = api ? (await api.checkPermissions()).display :
      (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission);
    if (!account) return permission;
    if (pendingTap) {
      if (pendingTap.account === account) onOpen?.(pendingTap.target);
      pendingTap = null;
    }
    const seen = ids(account);
    for (const item of items) {
      const id = String(item.id || '');
      if (!id) continue;
      if (item.read || item.readAt) { seen.add(id); displayed.get(id)?.close(); continue; }
      if (permission !== 'granted' || seen.has(id)) continue;
      // Reserve before delivery so concurrent checks/tabs do not normally repeat notices.
      const current = ids(account);
      if (current.has(id)) { seen.add(id); continue; }
      seen.add(id); save(account, seen);
      const review = item.kind === 'review_created' && item.reviewId;
      const title = review ? item.title || 'Новый отзыв' : 'Новый запрос';
      const target = review ? { section: 'reviews', reviewId: item.reviewId, notificationId: id } : { section: 'notifications' };
      const body = String(item.body || item.title || 'Откройте раздел запросов').slice(0, 180);
      try {
        if (api) {
          let next = Number(localStorage.getItem('tynys:request-notice-sequence') || 0) + 1;
          if (next > 2147483646) next = 1;
          localStorage.setItem('tynys:request-notice-sequence', String(next));
          await api.schedule({ notifications: [{ id: next, title, body, channelId: 'requests', extra: { account, target } }] });
        } else {
          const notice = new Notification(title, { body, tag: `request:${account}:${id}`, icon: '/assets/logo.svg' });
          notice.onclick = () => { if (activeAccount === account) { window.focus(); onOpen?.(target); } notice.close(); };
          displayed.set(id, notice);
        }
      } catch {
        seen.delete(id); save(account, seen);
      }
    }
    save(account, seen);
    return permission;
    };
    return globalThis.navigator?.locks
      ? navigator.locks.request('tynys-request-delivery', run)
      : run();
  });
  return queue;
}
