import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { portIsFree, selectAvailablePort } from '../../scripts/qa/available-port.mjs';

test('QA uses a free port other than personal and previous-test ports', async () => {
  const port = await selectAvailablePort();
  assert.ok(Number.isInteger(port) && port >= 1024);
  assert.notEqual(port, 8159);
  assert.notEqual(port, 8162);
  assert.equal(await portIsFree(port), true);
});

test('occupied port is not selected or stopped', async () => {
  const server = createServer();
  await new Promise((done, reject) => {
    server.once('error', reject);
    server.listen({ host: '127.0.0.1', port: 0 }, done);
  });
  const occupied = server.address().port;
  try {
    assert.equal(await portIsFree(occupied), false);
    assert.notEqual(await selectAvailablePort({ excluded: [occupied] }), occupied);
    assert.equal(server.listening, true);
  } finally {
    await new Promise((done, reject) => server.close(err => err ? reject(err) : done()));
  }
  assert.equal(await portIsFree(occupied), true);
});

test('invalid and privileged ports are rejected', async () => {
  for (const value of [0, 80, -1, 65536, 1.5, NaN])
    assert.equal(await portIsFree(value), false);
});

test('exhaustion fails without touching processes', async () => {
  await assert.rejects(selectAvailablePort({ attempts: 0 }), /No suitable/);
});
