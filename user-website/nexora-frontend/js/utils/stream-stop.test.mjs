import test from 'node:test';
import assert from 'node:assert/strict';
import { stopSessionAndCleanup } from './stream-stop.js';

test('backend stop confirmation is retained when WHIP cleanup fails', async () => {
  let stopRequested = false;
  const result = await stopSessionAndCleanup(
    async () => { stopRequested = true; return { id: 'stream_test', status: 'STOPPING' }; },
    async () => { throw new Error('cleanup unavailable'); }
  );
  assert.equal(stopRequested, true);
  assert.equal(result.session.status, 'STOPPING');
  assert.match(result.cleanupError.message, /cleanup unavailable/);
});

test('failed backend stop is not treated as confirmation even if cleanup succeeds', async () => {
  await assert.rejects(
    stopSessionAndCleanup(async () => { throw new Error('backend unavailable'); }, async () => null),
    /backend unavailable/
  );
});

test('backend and capture cleanup run once together for one stop operation', async () => {
  const calls = [];
  const result = await stopSessionAndCleanup(
    async () => { calls.push('backend'); return { status: 'STOPPED' }; },
    async () => { calls.push('cleanup'); return null; }
  );
  assert.deepEqual(calls.sort(), ['backend', 'cleanup']);
  assert.equal(result.session.status, 'STOPPED');
  assert.equal(result.cleanupError, null);
});
