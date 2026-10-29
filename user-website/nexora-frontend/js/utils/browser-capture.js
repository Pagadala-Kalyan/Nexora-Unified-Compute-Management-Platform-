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

export async function requestCameraCapture(mediaDevices = globalThis.navigator?.mediaDevices) {
  if (!mediaDevices || typeof mediaDevices.getUserMedia !== 'function') {
    throw new Error('Camera capture is not supported by this browser. Use a current Chrome, Edge, or Firefox browser over HTTPS or localhost.');
  }

  try {
    const stream = await mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
      audio: true
    });
    if (!stream?.getVideoTracks?.().length) {
      stopMediaStream(stream);
      throw new Error('The selected camera did not provide a video track. Check camera permissions.');
    }
    return stream;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('The selected camera')) throw error;
    if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') {
      throw new Error('Camera access permission was denied. Allow camera permissions in your browser and try again.');
    }
    if (error?.name === 'NotFoundError' || error?.name === 'DevicesNotFoundError') {
      throw new Error('No camera or webcam was found on this device.');
    }
    throw new Error(`Could not access camera: ${error.message || 'Check camera permissions and try again.'}`);
  }
}

export function createSimulatedMediaStream() {
  const canvas = document.createElement('canvas');
  canvas.width = 1280;
  canvas.height = 720;
  const ctx = canvas.getContext('2d');
  
  let frame = 0;
  let animId = null;

  function draw() {
    frame++;
    const now = new Date();
    
    // Gradient futuristic background
    const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    grad.addColorStop(0, '#0a0d18');
    grad.addColorStop(0.5, '#121829');
    grad.addColorStop(1, '#070912');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grid lines
    ctx.strokeStyle = 'rgba(74, 222, 128, 0.08)';
    ctx.lineWidth = 1;
    for (let x = 0; x < canvas.width; x += 40) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }

    // Animated rotating radar circle
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const angle = (frame * 0.03) % (Math.PI * 2);
    ctx.strokeStyle = '#00f0ff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, 120, 0, Math.PI * 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle) * 120, cy + Math.sin(angle) * 120);
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.8)';
    ctx.stroke();

    // Pulse center dot
    const pulse = Math.sin(frame * 0.1) * 6 + 12;
    ctx.fillStyle = '#ff0055';
    ctx.beginPath();
    ctx.arc(cx, cy, pulse, 0, Math.PI * 2);
    ctx.fill();

    // Header badge
    ctx.fillStyle = '#00f0ff';
    ctx.font = 'bold 28px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('NEXORA BROADCAST ENGINE', cx, 100);

    ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
    ctx.font = '16px monospace';
    ctx.fillText('LIVE SIMULATED INPUT • 720p60 • WEBRTC WHIP TEST', cx, 135);

    // Timecode & Frame counter
    const timecode = now.toISOString().replace('T', ' ').slice(0, 23);
    ctx.fillStyle = '#39d353';
    ctx.font = 'bold 36px monospace';
    ctx.fillText(timecode, cx, 540);

    ctx.fillStyle = '#a78bfa';
    ctx.font = '18px monospace';
    ctx.fillText(`FRAME: ${frame} | FPS: 60 | AUDIO: SYNTH OSCILLATOR`, cx, 580);

    // Waveform at bottom
    ctx.strokeStyle = '#00f0ff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < canvas.width; i += 10) {
      const h = Math.sin((i + frame * 5) * 0.05) * 20;
      if (i === 0) ctx.moveTo(i, 650 + h);
      else ctx.lineTo(i, 650 + h);
    }
    ctx.stroke();

    animId = requestAnimationFrame(draw);
  }

  draw();

  const stream = canvas.captureStream ? canvas.captureStream(30) : null;
  if (!stream) {
    throw new Error('Canvas captureStream is not supported in this environment.');
  }

  try {
    const AudioCtx = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (AudioCtx) {
      const audioCtx = new AudioCtx();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      gain.gain.value = 0.01;
      osc.frequency.value = 440;
      const dest = audioCtx.createMediaStreamDestination();
      osc.connect(gain);
      gain.connect(dest);
      osc.start();
      const audioTrack = dest.stream?.getAudioTracks?.()[0];
      if (audioTrack) {
        stream.addTrack(audioTrack);
        audioTrack.addEventListener('ended', () => {
          try { osc.stop(); audioCtx.close(); } catch (_) {}
        });
      }
    }
  } catch (_) {}

  const videoTrack = stream.getVideoTracks()[0];
  if (videoTrack) {
    const origStop = videoTrack.stop.bind(videoTrack);
    videoTrack.stop = () => {
      if (animId) cancelAnimationFrame(animId);
      origStop();
    };
  }

  return stream;
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

