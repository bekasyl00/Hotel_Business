import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { includeApiFile, validateApiConfig } from '../scripts/package-api.mjs';

test('API package rejects website routing, including a self-proxy', async () => {
  const backend = JSON.parse(await readFile(new URL('../backend/vercel.json', import.meta.url)));
  const website = JSON.parse(await readFile(new URL('../vercel.json', import.meta.url)));
  assert.doesNotThrow(() => validateApiConfig(backend));
  assert.throws(() => validateApiConfig(website));
  assert.throws(() => validateApiConfig({ ...backend, routes: website.routes }));
  assert.throws(() => validateApiConfig({ ...backend, rewrites: [{ source: '/api/:path*', destination: 'https://tynys-api.vercel.app/api/:path*' }] }));
});

test('API packaging excludes local secrets, tests and generated storage', () => {
  for (const path of ['backend/.env.stage', 'backend/.env.example', 'backend/.venv/bin/python', 'backend/.vercel/project.json', 'backend/private-media/file.pdf', 'backend/booking/tests.py', 'backend/commerce/test_refunds.py', 'backend/pyproject.toml', 'src/main.js']) {
    assert.equal(includeApiFile(path), false, path);
  }
  for (const path of ['backend/vercel.json', 'backend/.python-version', 'backend/requirements.txt', 'backend/booking/migrations/0022_booking_public_code.py', 'backend/commerce/accounting/templates/act.xlsx', 'backend/config/wsgi.py']) {
    assert.equal(includeApiFile(path), true, path);
  }
});
