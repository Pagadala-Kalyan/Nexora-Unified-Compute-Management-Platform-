import test from 'node:test';
import assert from 'node:assert/strict';
import { requestBrowserCapture, startWhipPublisher, stopMediaStream } from './browser-capture.js';

test('screen permission denial is reported clearly', async () => {
  const mediaDevices = {
    getDisplayMedia: async () => { throw Object.assign(new Error('denied'), { name: 'NotAllowedError' }); }
  };
  await assert.rejects(requestBrowserCapture(mediaDevices), /permission was denied or cancelled/);
});

test('unsupported browser capture is reported without calling a capture API', async () => {
  await assert.rejects(requestBrowserCapture({}), /not supported by this browser/);
});

test('WHIP offer negotiates with scoped Basic auth and closes its session', async () => {
  const requests = [];
  class PeerConnectionFake {
    iceGatheringState = 'complete';
    connectionState = 'connected';
    localDescription = null;
    closed = false;
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    async setRemoteDescription(value) { this.remoteDescription = value; }
    addEventListener() {}
    removeEventListener() {}
    close() { this.closed = true; }
  }
  const publisher = await startWhipPublisher({
    endpoint: 'http://127.0.0.1:8889/live/stream_test/whip',
    stream: { getTracks: () => [{ kind: 'video' }] },
    username: 'nexora',
    password: 'session-only-password',
    PeerConnection: PeerConnectionFake,
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      if (options.method === 'POST') {
        return { ok: true, headers: { get: () => '/live/stream_test/whip/resource' }, text: async () => 'answer-sdp' };
      }
      return { ok: true };
    }
  });
  assert.equal(requests[0].options.method, 'POST');
  assert.equal(requests[0].options.body, 'offer-sdp');
  assert.equal(requests[0].options.headers.Authorization, `Basic ${btoa('nexora:session-only-password')}`);
  assert.equal(requests[0].url.includes('session-only-password'), false);
  await publisher.close();
  assert.equal(requests[1].options.method, 'DELETE');
  assert.equal(requests[1].url, 'http://127.0.0.1:8889/live/stream_test/whip/resource');
  await publisher.close();
  assert.equal(requests.length, 2, 'closing twice must not send a second DELETE');
});

test('WHIP authorization failure is human readable and closes the peer', async () => {
  let peer;
  class PeerConnectionFake {
    constructor() { peer = this; this.iceGatheringState = 'complete'; }
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    addEventListener() {}
    removeEventListener() {}
    close() { this.closed = true; }
  }
  await assert.rejects(startWhipPublisher({
    endpoint: 'http://127.0.0.1:8889/live/stream_test/whip',
    stream: { getTracks: () => [] }, username: 'nexora', password: 'private-key',
    PeerConnection: PeerConnectionFake,
    fetchImpl: async () => ({ ok: false, status: 401 })
  }), /rejected this session’s publish credential/);
  assert.equal(peer.closed, true);
});

test('inactive session callback explains the provider input timeout without exposing credentials', async () => {
  class PeerConnectionFake {
    constructor() { this.iceGatheringState = 'complete'; }
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    addEventListener() {}
    removeEventListener() {}
    close() {}
  }
  await assert.rejects(startWhipPublisher({
    endpoint: 'http://127.0.0.1:8889/live/stream_test/whip',
    stream: { getTracks: () => [] }, username: 'nexora', password: 'private-key',
    PeerConnection: PeerConnectionFake,
    fetchImpl: async () => ({
      ok: false, status: 401,
      json: async () => ({ detail: 'Invalid session or session not active' }),
    })
  }), /session ended before browser publishing connected/);
});

test('an HTTPS website rejects insecure remote WHIP signaling', async () => {
  const previousLocation = globalThis.location;
  Object.defineProperty(globalThis, 'location', { value: { protocol: 'https:' }, configurable: true });
  try {
    await assert.rejects(startWhipPublisher({
      endpoint: 'http://media.example.test:8889/live/session/whip',
      stream: { getTracks: () => [] }, username: 'nexora', password: 'session-key',
      PeerConnection: class {}, fetchImpl: async () => { throw new Error('must not fetch'); }
    }), /requires an HTTPS MEDIAMTX_WEBRTC_URL/);
  } finally {
    if (previousLocation === undefined) delete globalThis.location;
    else Object.defineProperty(globalThis, 'location', { value: previousLocation, configurable: true });
  }
});

test('WHIP network failure gives a useful MediaMTX endpoint message instead of Failed to fetch', async () => {
  class PeerConnectionFake {
    constructor() { this.iceGatheringState = 'complete'; }
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    addEventListener() {}
    removeEventListener() {}
    close() {}
  }
  await assert.rejects(startWhipPublisher({
    endpoint: 'http://127.0.0.1:8889/live/stream_test/whip',
    stream: { getTracks: () => [] }, username: 'nexora', password: 'private-key',
    PeerConnection: PeerConnectionFake,
    fetchImpl: async () => { throw new TypeError('Failed to fetch'); }
  }), /could not reach MediaMTX WHIP.*port 8889.*CORS origin/);
});

test('WHIP cleanup reports failure, closes the peer, and remains idempotent', async () => {
  let peer;
  let deletes = 0;
  class PeerConnectionFake {
    constructor() { peer = this; this.iceGatheringState = 'complete'; this.connectionState = 'connected'; }
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'offer-sdp' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    async setRemoteDescription() {}
    addEventListener() {}
    removeEventListener() {}
    close() { this.closed = true; }
  }
  const publisher = await startWhipPublisher({
    endpoint: 'http://127.0.0.1:8889/live/stream_test/whip',
    stream: { getTracks: () => [] }, username: 'nexora', password: 'private-key',
    PeerConnection: PeerConnectionFake,
    fetchImpl: async (_url, options) => options.method === 'POST'
      ? { ok: true, headers: { get: () => '/resource' }, text: async () => 'answer-sdp' }
      : (++deletes, { ok: false, status: 500 })
  });
  const first = await publisher.close();
  const second = await publisher.close();
  assert.equal(first.cleanupError.message, 'MediaMTX did not confirm browser publisher cleanup (HTTP 500).');
  assert.equal(second.cleanupError.message, first.cleanupError.message);
  assert.equal(deletes, 1);
  assert.equal(peer.closed, true);
});

test('capture cleanup stops every local media track', () => {
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }, { stopped: false, stop() { this.stopped = true; } }];
  stopMediaStream({ getTracks: () => tracks });
  assert.ok(tracks.every(track => track.stopped));
});
