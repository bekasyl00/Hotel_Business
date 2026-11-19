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

test('a new review has its own banner and opens the exact review only for its recipient', async () => {
  const h = harness();
  const targets = [];
  await h.requestDeliveryPermission();
  const item = { id: 'event', kind: 'review_created', reviewId: 'review', title: 'Жаңа пікір', body: 'Resort · 4/5' };
  const open = target => targets.push(target);
  await h.deliverLocalRequests('owner', [item], open);
  await h.deliverLocalRequests('owner', [item], open);
  assert.equal(h.notices.length, 1);
  assert.equal(h.notices[0].title, item.title);
  assert.equal(h.notices[0].body, item.body);
  h.notices[0].onclick();
  assert.deepEqual(targets, [{ section: 'reviews', reviewId: 'review', notificationId: 'event' }]);
  await h.deliverLocalRequests('other', [], open);
  h.notices[0].onclick();
  assert.equal(targets.length, 1);
});

test('Android schedules one high importance review notice and its tap opens the review', async () => {
  const scheduled = [], values = new Map(), targets = [];
  let listener, channel;
  const api = {
    createChannel: async value => { channel = value; },
    addListener: async (_, fn) => { listener = fn; },
    checkPermissions: async () => ({ display: 'granted' }),
    getPending: async () => ({ notifications: [] }),
    cancel: async () => {}, removeAllDeliveredNotifications: async () => {},
    schedule: async ({ notifications }) => scheduled.push(...notifications),
  };
  const source = readFileSync(new URL('../src/shared/native/local-request-delivery.js', import.meta.url), 'utf8')
    .replace(/^import .*;$/gm, '').replace(/export /g, '')
    .replace(/await import\('@capacitor\/local-notifications'\)/g, '({ LocalNotifications: api })');
  const deliver = new Function('Capacitor', 'api', 'localStorage', source + '\nreturn deliverLocalRequests;')(
    { getPlatform: () => 'android' }, api,
    { getItem: k => values.get(k) || null, setItem: (k,v) => values.set(k,v) });
  const item = { id: 'n2', kind: 'review_created', reviewId: 'r2', title: 'Новый отзыв', body: 'Hotel · 5/5' };
  const tap = target => targets.push(target);
  await deliver('manager', [item], tap);
  await deliver('manager', [item], tap);
  assert.equal(channel.importance, 5);
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0].title, item.title);
  assert.equal(scheduled[0].channelId, channel.id);
  listener({ notification: scheduled[0] });
  assert.deepEqual(targets, [{ section: 'reviews', reviewId: 'r2', notificationId: 'n2' }]);
});
