// Foreground request delivery; no Firebase, APNs or remote push.
import { Capacitor } from '@capacitor/core';
let android;
let activeAccount = '';
let onOpen;
let queue = Promise.resolve();
const displayed = new Map();
const key = (account) => `tynys:request-notices:${account}`;
const ids = (account) => { try { return new Set(JSON.parse(localStorage.getItem(key(account)) || '[]')); } catch { return new Set(); } };
const save = (account, seen) => localStorage.setItem(key(account), JSON.stringify([...seen]));

async function plugin() {
  if (!android) {
    android = (await import('@capacitor/local-notifications')).LocalNotifications;
    await android.createChannel({ id: 'requests', name: 'Запросы', importance: 5, vibration: true }).catch(() => {}); // Android <26 has no channels.
    await android.addListener('localNotificationActionPerformed', ({ notification }) => {
      if (notification.extra?.account === activeAccount && activeAccount) onOpen?.();
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
      if (api) {
        await api.cancel(await api.getPending());
        await api.removeAllDeliveredNotifications();
      }
      activeAccount = account;
    }
    const permission = api ? (await api.checkPermissions()).display :
      (typeof Notification === 'undefined' ? 'unsupported' : Notification.permission);
    if (!account) return permission;
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
      const body = String(item.body || item.title || 'Откройте раздел запросов').slice(0, 180);
      try {
        if (api) {
          let next = Number(localStorage.getItem('tynys:request-notice-sequence') || 0) + 1;
          if (next > 2147483646) next = 1;
          localStorage.setItem('tynys:request-notice-sequence', String(next));
          await api.schedule({ notifications: [{ id: next, title: 'Новый запрос', body, channelId: 'requests', extra: { account } }] });
        } else {
          const notice = new Notification('Новый запрос', { body, tag: `request:${account}:${id}`, icon: '/assets/logo.svg' });
          notice.onclick = () => { if (activeAccount === account) { window.focus(); onOpen?.(); } notice.close(); };
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
