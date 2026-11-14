import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as vue from 'vue';

function load(plugin) {
  const source = readFileSync(new URL('../src/shared/native/push.js', import.meta.url), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace(/export /g, '');
  return new Function('reactive', 'ref', 'Capacitor', 'registerPlugin', 'isNativePushAvailable', 'deliverLocalRequests', 'requestDeliveryPermission', source +
    '\nreturn { syncLocalRequests, syncStaffPushSession, revokeStaffPushDevice, staffPushState, pendingPushTarget };')(
      vue.reactive, vue.ref, { isNativePlatform: () => true, getPlatform: () => 'ios' }, () => plugin, () => false);
}

test('local iOS does not register remote push; section permission and tap target use the local bridge', async () => {
  const calls = [];
  const state = load({ addListener: async () => {}, localRequests: async (args) => {
    calls.push(args);
    return { permission: args.askPermission ? 'denied' : 'prompt', openRequests: args.items.length > 0 };
  }});
  const user = { id: 'manager-a', role: 'manager' };
  await state.syncStaffPushSession(user, () => { throw Error('remote API forbidden'); });
  assert.equal(calls[0].askPermission, false);
  await state.syncLocalRequests(user, [{ id: 'request-1' }], true);
  assert.equal(state.staffPushState.permission, 'denied');
  assert.deepEqual(state.pendingPushTarget.value, { section: 'notifications' });
  assert.equal(calls[1].account, 'manager-a');
  await state.revokeStaffPushDevice();
  assert.equal(calls.at(-1).account, '');
});

test('local notification failures are silent and accountants never receive a local account scope', async () => {
  let account;
  const state = load({ addListener: async () => {}, localRequests: async (args) => {
    account = args.account;
    throw Error('permission unavailable');
  }});
  await state.syncLocalRequests({ id: 'finance', role: 'accountant' }, [], true);
  assert.equal(account, '');
  assert.equal(state.staffPushState.error, '');
});
