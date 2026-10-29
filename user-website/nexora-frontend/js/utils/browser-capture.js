const CAPTURE_CONSTRAINTS = {
  video: { frameRate: { ideal: 30, max: 60 } },
  audio: true
};

export async function requestBrowserCapture(mediaDevices = globalThis.navigator?.mediaDevices) {
  if (!mediaDevices || typeof mediaDevices.getDisplayMedia !== 'function') {
    throw new Error('Screen capture is not supported by this browser. Use a current Chrome, Edge, or Firefox browser over HTTPS or localhost.');
  }

  try {
    const stream = await mediaDevices.getDisplayMedia(CAPTURE_CONSTRAINTS);
    if (!stream?.getVideoTracks?.().length) {
      stopMediaStream(stream);
      throw new Error('The selected screen source did not provide a video track. Try sharing a screen, window, or tab.');
    }
    return stream;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('The selected screen source')) throw error;
    if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
      throw new Error('Screen capture permission was denied or cancelled. Allow screen sharing in the browser prompt and try again.');
    }
    if (error?.name === 'NotFoundError') {
      throw new Error('No screen, window, or tab is available to share.');
    }
    throw new Error('The browser could not start screen capture. Check browser permissions and try again.');
  }
}

export function stopMediaStream(stream) {
  for (const track of stream?.getTracks?.() || []) {
    track.onended = null;
    try { track.stop(); } catch (_) { /* already stopped by the browser */ }
  }
}

function waitForIceGathering(peer, timeoutMs) {
  if (peer.iceGatheringState === 'complete') return Promise.resolve();
  return new Promise((resolve, reject) => {
    const finish = (error) => {
      clearTimeout(timer);
      peer.removeEventListener('icegatheringstatechange', onState);
      if (error) reject(error); else resolve();
    };
    const onState = () => {
      if (peer.iceGatheringState === 'complete') finish();
    };
    const timer = setTimeout(() => finish(new Error('Timed out while preparing the browser media connection.')), timeoutMs);
    peer.addEventListener('icegatheringstatechange', onState);
  });
}

function waitForConnected(peer, timeoutMs) {
  if (peer.connectionState === 'connected') return Promise.resolve();
  return new Promise((resolve, reject) => {
    const finish = (error) => {
      clearTimeout(timer);
      peer.removeEventListener('connectionstatechange', onState);
      if (error) reject(error); else resolve();
    };
    const onState = () => {
      if (peer.connectionState === 'connected') finish();
      else if (peer.connectionState === 'failed' || peer.connectionState === 'closed') {
        finish(new Error('The browser could not establish a media connection to Nexora. Check MediaMTX address, firewall, and WebRTC settings.'));
      }
    };
    const timer = setTimeout(() => finish(new Error('Timed out connecting browser media to Nexora. Check the MediaMTX WebRTC address and network.')), timeoutMs);
    peer.addEventListener('connectionstatechange', onState);
  });
}

export async function startWhipPublisher({
  endpoint,
  stream,
  username,
  password,
  fetchImpl = globalThis.fetch,
  PeerConnection = globalThis.RTCPeerConnection,
  timeoutMs = 20000
}) {
  if (typeof PeerConnection !== 'function' || typeof fetchImpl !== 'function') {
    throw new Error('This browser does not support the WebRTC publishing features required for Browser Capture.');
  }
  let target;
  try { target = new URL(endpoint); } catch (_) {
    throw new Error('Nexora did not provide a valid browser ingest address. Check MEDIAMTX_WEBRTC_URL.');
  }
  if (!['http:', 'https:'].includes(target.protocol) || !target.hostname || !username || !password) {
    throw new Error('Browser ingest settings or the session publish credential are invalid. Recreate the stream session.');
  }
  if (globalThis.location?.protocol === 'https:' && target.protocol !== 'https:') {
    throw new Error('Browser Capture from this secure website requires an HTTPS MEDIAMTX_WEBRTC_URL. Configure MediaMTX behind TLS and try again.');
  }

  const peer = new PeerConnection({ iceServers: [] });
  let resourceUrl = null;
  const authorization = `Basic ${btoa(`${username}:${password}`)}`;
  try {
    for (const track of stream.getTracks()) peer.addTrack(track, stream);
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    await waitForIceGathering(peer, timeoutMs);

    const requestController = new AbortController();
    const requestTimer = setTimeout(() => requestController.abort(), timeoutMs);
    let response;
    try {
      response = await fetchImpl(target.href, {
      method: 'POST',
      headers: { Authorization: authorization, 'Content-Type': 'application/sdp', Accept: 'application/sdp' },
        body: peer.localDescription.sdp,
        signal: requestController.signal
      });
    } finally {
      clearTimeout(requestTimer);
    }
    if (!response.ok) {
      let callbackDetail = '';
      if (response.status === 401 || response.status === 403) {
        try {
          const body = await response.json();
          callbackDetail = typeof body?.detail === 'string' ? body.detail : '';
        } catch (_) { /* MediaMTX may return an empty or non-JSON rejection */ }
      }
      const reason = callbackDetail === 'Invalid session or session not active'
        ? 'This Nexora session ended before browser publishing connected. Start a new session and begin screen sharing before the provider input timeout.'
        : response.status === 401 || response.status === 403
          ? 'MediaMTX rejected this session’s publish credential. Recreate the session and try again.'
        : `MediaMTX could not start browser publishing (HTTP ${response.status}). Check its WebRTC listener and CORS settings.`;
      throw new Error(reason);
    }
    const location = response.headers.get('Location');
    const answer = await response.text();
    if (!location || !answer) throw new Error('MediaMTX returned an incomplete WHIP response. Check its version and WHIP endpoint.');
    resourceUrl = new URL(location, target).href;
    await peer.setRemoteDescription({ type: 'answer', sdp: answer });
    await waitForConnected(peer, timeoutMs);

    let closePromise = null;
    return {
      async close() {
        if (closePromise) return closePromise;
        closePromise = (async () => {
          let cleanupError = null;
          try {
            if (resourceUrl) {
              const controller = new AbortController();
              const timer = setTimeout(() => controller.abort(), 3000);
              let response;
              try { response = await fetchImpl(resourceUrl, { method: 'DELETE', headers: { Authorization: authorization }, signal: controller.signal }); }
              finally { clearTimeout(timer); }
              // A resource already removed by MediaMTX is an idempotent success.
              if (!response.ok && response.status !== 404 && response.status !== 410) {
                cleanupError = new Error(`MediaMTX did not confirm browser publisher cleanup (HTTP ${response.status}).`);
              }
          }
          } catch (_) {
            cleanupError = new Error('Could not reach MediaMTX to confirm browser publisher cleanup. Local capture was stopped.');
          } finally {
            peer.close();
          }
          return { cleanupError };
        })();
        return closePromise;
      }
    };
  } catch (error) {
    let cleanupFailed = false;
    if (resourceUrl) {
      try {
        const response = await fetchImpl(resourceUrl, { method: 'DELETE', headers: { Authorization: authorization } });
        cleanupFailed = !response.ok && response.status !== 404 && response.status !== 410;
      } catch (_) {
        cleanupFailed = true;
      }
    }
    peer.close();
    const cleanupNote = cleanupFailed ? ' MediaMTX cleanup of the partial publisher could not be confirmed.' : '';
    if (error?.name === 'AbortError') {
      throw new Error(`Timed out while contacting MediaMTX WHIP. Check the configured WebRTC URL, port 8889, and network connectivity.${cleanupNote}`);
    }
    if (error?.name === 'TypeError' || /failed to fetch/i.test(error?.message || '')) {
      throw new Error(`The browser could not reach MediaMTX WHIP. Verify MEDIAMTX_WEBRTC_URL, port 8889, the allowed frontend CORS origin, and network connectivity.${cleanupNote}`);
    }
    if (error instanceof Error && error.message && !error.message.includes(username) && !error.message.includes(password)) {
      if (cleanupNote) error.message += cleanupNote;
      throw error;
    }
    throw new Error(`Browser publishing could not be established. Check the Nexora MediaMTX configuration and try again.${cleanupNote}`);
  }
}

