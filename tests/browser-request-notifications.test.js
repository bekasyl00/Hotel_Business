import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
function harness() {
  const values = new Map(), notices = [];
  class Notification {
    static permission = 'default';
    static async requestPermission() { this.permission = 'granted'; return 'granted'; }
    constructor(title, options) { Object.assign(this, { title, ...options }); notices.push(this); }
    close() { this.closed = true; }
  }
  const source = readFileSync(new URL('../src/shared/native/local-request-delivery.js', import.meta.url), 'utf8')
    .replace(/^import .*;$/gm, '').replace(/export /g, '');
  const service = new Function('Capacitor', 'Notification', 'localStorage', 'window', source + '\nreturn {deliverLocalRequests, requestDeliveryPermission};')(
    { getPlatform: () => 'web' }, Notification,
    { getItem: k => values.get(k) || null, setItem: (k,v) => values.set(k,v) }, { focus() {} });
  return { ...service, notices, Notification };
}
test('browser permission is explicit; unread IDs notify once, read IDs never notify, and click routes', async () => {
  const h = harness(); let opened = 0;
  const items = [{ id: 'one', body: 'Новая бронь' }, { id: 'seen', readAt: 'today' }];
  await h.deliverLocalRequests('manager', items, () => opened++);
  assert.equal(h.notices.length, 0);
  await h.requestDeliveryPermission();
  await Promise.all([h.deliverLocalRequests('manager', items, () => opened++), h.deliverLocalRequests('manager', items, () => opened++)]);
  assert.equal(h.notices.length, 1);
  h.notices[0].onclick(); assert.equal(opened, 1);
  await h.deliverLocalRequests('', [], () => opened++);
  h.notices[0].onclick(); assert.equal(opened, 1);
  await h.deliverLocalRequests('manager', items, () => opened++);
  assert.equal(h.notices.length, 1);
});
test('denied browser permission remains silent', async () => {
  const h = harness(); h.Notification.permission = 'denied';
  assert.equal(await h.deliverLocalRequests('manager', [{id:'new'}], () => {}), 'denied');
  assert.equal(h.notices.length, 0);
});
