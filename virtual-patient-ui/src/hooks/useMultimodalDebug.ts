import {useEffect, useRef, useState} from 'react';
import {
  DebugUnavailable,
  OpenSmileFrameDebug,
  PyFeatFrameDebug,
  isDebugUnavailable,
  postDebugAudio,
  postDebugFrame,
} from '../services/debug';

// DEV/DEBUG-ONLY hook that OBSERVES the existing calibration media streams and
// samples raw, frame-level multimodal observations. It never calls getUserMedia
// and never stops or mutates the streams owned by the interview media context.
// When disabled it performs no work and reports null latest values.

export type MultimodalDebugOptions = {
  enabled: boolean;
  cameraStream: MediaStream | null;
  microphoneStream: MediaStream | null;
  // The preview <video>. When not yet ready the hook falls back to a hidden
  // video bound to cameraStream so sampling can still start.
  videoEl: HTMLVideoElement | null;
  // Target frame sampling rate (frames per second). Backpressure may reduce the
  // effective rate below this target.
  frameFps?: number;
  // Interval between self-contained audio chunks (ms).
  audioIntervalMs?: number;
};

export type MultimodalDebugState = {
  pyfeat: PyFeatFrameDebug | DebugUnavailable | null;
  opensmile: OpenSmileFrameDebug | DebugUnavailable | null;
  // Latest measured frame extractor latency (ms) and effective sampling rate.
  frameProcessingMs: number | null;
  sampleFps: number | null;
};

// Detectorv2 on CPU is an inspection aid rather than a real-time renderer.
// One frame per second remains useful in calibration while preventing the debug
// panel from competing with audio extraction and API health checks.
const DEFAULT_FRAME_FPS = 1;
const DEFAULT_AUDIO_INTERVAL_MS = 1_500;
const JPEG_QUALITY = 0.7;
const MAX_DEBUG_FRAME_EDGE_PX = 640;

// Ordered candidate MIME types for the debug MediaRecorder. The first supported
// one that ffmpeg can decode is used; each chunk is produced by a start/stop
// cycle so it is self-contained.
const AUDIO_MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/ogg',
  'audio/mp4',
];

const pickAudioMimeType = (): string | undefined => {
  if (typeof MediaRecorder === 'undefined') return undefined;
  return AUDIO_MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
};

// Draws the current video frame onto an offscreen canvas (sized to the raw,
// UNMIRRORED video frame) and returns a JPEG blob. Returns null when the video
// has no decodable frame yet. Exported for unit testing.
export const captureFrameBlob = (
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
): Promise<Blob | null> => {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return Promise.resolve(null);
  const scale = Math.min(1, MAX_DEBUG_FRAME_EDGE_PX / Math.max(width, height));
  const sampledWidth = Math.max(1, Math.round(width * scale));
  const sampledHeight = Math.max(1, Math.round(height * scale));
  if (canvas.width !== sampledWidth) canvas.width = sampledWidth;
  if (canvas.height !== sampledHeight) canvas.height = sampledHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) return Promise.resolve(null);
  // Draw the raw frame (no mirroring) so backend landmark pixel coordinates map
  // to the real image; the overlay handles mirroring for display only.
  ctx.drawImage(video, 0, 0, sampledWidth, sampledHeight);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), 'image/jpeg', JPEG_QUALITY);
  });
};

export const useMultimodalDebug = (
  options: MultimodalDebugOptions,
): MultimodalDebugState => {
  const {
    enabled,
    cameraStream,
    microphoneStream,
    videoEl,
    frameFps = DEFAULT_FRAME_FPS,
    audioIntervalMs = DEFAULT_AUDIO_INTERVAL_MS,
  } = options;

  const [pyfeat, setPyfeat] = useState<PyFeatFrameDebug | DebugUnavailable | null>(null);
  const [opensmile, setOpensmile] = useState<OpenSmileFrameDebug | DebugUnavailable | null>(null);
  const [frameProcessingMs, setFrameProcessingMs] = useState<number | null>(null);
  const [sampleFps, setSampleFps] = useState<number | null>(null);

  // Latest option values, so the long-lived sampling loops read current props
  // without being torn down on every render.
  const videoElRef = useRef<HTMLVideoElement | null>(videoEl);
  videoElRef.current = videoEl;
  const cameraStreamRef = useRef<MediaStream | null>(cameraStream);
  cameraStreamRef.current = cameraStream;

  // ---- Frame sampling -----------------------------------------------------
  useEffect(() => {
    if (!enabled) return undefined;

    let stopped = false;
    const canvas = document.createElement('canvas');
    // Hidden fallback video, created lazily only if the preview element is not
    // ready. Bound to cameraStream so we can still read frames.
    let fallbackVideo: HTMLVideoElement | null = null;
    let controller: AbortController | null = null;
    let inFlight = false;
    let lastSampleAt = 0;

    const getSourceVideo = (): HTMLVideoElement | null => {
      const preview = videoElRef.current;
      if (preview && preview.videoWidth > 0) return preview;
      const stream = cameraStreamRef.current;
      if (!stream) return preview ?? null;
      if (!fallbackVideo) {
        fallbackVideo = document.createElement('video');
        fallbackVideo.muted = true;
        fallbackVideo.playsInline = true;
        fallbackVideo.srcObject = stream;
        void fallbackVideo.play().catch(() => undefined);
      } else if (fallbackVideo.srcObject !== stream) {
        fallbackVideo.srcObject = stream;
      }
      return fallbackVideo.videoWidth > 0 ? fallbackVideo : (preview ?? null);
    };

    const tick = async () => {
      if (stopped || inFlight) return;
      const video = getSourceVideo();
      if (!video) return;
      const blob = await captureFrameBlob(video, canvas);
      if (stopped || !blob) return;
      inFlight = true;
      const now = performance.now();
      // Effective sampling rate from the gap since the previous dispatched tick.
      if (lastSampleAt > 0) {
        const deltaMs = now - lastSampleAt;
        if (deltaMs > 0) setSampleFps(Math.round((1000 / deltaMs) * 10) / 10);
      }
      lastSampleAt = now;
      controller = new AbortController();
      try {
        const result = await postDebugFrame(blob, Date.now(), controller.signal);
        if (stopped) return;
        setPyfeat(result);
        if (!isDebugUnavailable(result)) setFrameProcessingMs(result.processingMs);
      } catch (error) {
        if ((error as Error)?.name !== 'AbortError' && !stopped) {
          // Keep the previous observation; a transient error should not clear it.
        }
      } finally {
        inFlight = false;
      }
    };

    const intervalMs = Math.max(1, Math.round(1000 / Math.max(0.1, frameFps)));
    const interval = window.setInterval(() => void tick(), intervalMs);

    return () => {
      stopped = true;
      window.clearInterval(interval);
      controller?.abort();
      if (fallbackVideo) {
        fallbackVideo.srcObject = null;
        fallbackVideo = null;
      }
      // Drop the offscreen canvas backing store.
      canvas.width = 0;
      canvas.height = 0;
    };
  }, [enabled, frameFps]);

  // ---- Audio sampling -----------------------------------------------------
  useEffect(() => {
    if (!enabled || !microphoneStream) return undefined;
    const track = microphoneStream.getAudioTracks()[0];
    if (!track || typeof MediaRecorder === 'undefined') return undefined;

    let stopped = false;
    let controller: AbortController | null = null;
    let inFlight = false;
    let recorder: MediaRecorder | null = null;
    let cycleTimeout: number | null = null;
    // Clone the track so stopping the debug recorder never affects the main
    // microphone track owned by the media context.
    const clonedTrack = track.clone();
    const debugStream = new MediaStream([clonedTrack]);
    const mimeType = pickAudioMimeType();

    const send = async (blob: Blob) => {
      if (stopped || inFlight || blob.size === 0) return;
      inFlight = true;
      controller = new AbortController();
      try {
        const result = await postDebugAudio(blob, Date.now(), controller.signal);
        if (!stopped) setOpensmile(result);
      } catch (error) {
        if ((error as Error)?.name !== 'AbortError' && !stopped) {
          // Keep the previous observation on transient failure.
        }
      } finally {
        inFlight = false;
      }
    };

    // Each cycle records for `audioIntervalMs` then stops, producing a
    // self-contained chunk. A fresh recorder per cycle guarantees the blob is
    // independently decodable and prevents unbounded buffer growth.
    const runCycle = () => {
      if (stopped || clonedTrack.readyState !== 'live') return;
      let chunk: Blob | null = null;
      try {
        recorder = mimeType
          ? new MediaRecorder(debugStream, {mimeType})
          : new MediaRecorder(debugStream);
      } catch {
        return;
      }
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) chunk = event.data;
      };
      recorder.onstop = () => {
        recorder = null;
        if (stopped) return;
        // Only dispatch the freshest chunk; drop it if a request is in flight
        // (backpressure) so nothing queues up.
        if (chunk) void send(chunk);
        // Schedule the next cycle so sampling continues.
        cycleTimeout = window.setTimeout(runCycle, 0);
      };
      try {
        recorder.start();
      } catch {
        recorder = null;
        if (!stopped) cycleTimeout = window.setTimeout(runCycle, audioIntervalMs);
        return;
      }
      cycleTimeout = window.setTimeout(() => {
        if (recorder && recorder.state !== 'inactive') {
          try {
            recorder.stop();
          } catch {
            recorder = null;
          }
        }
      }, audioIntervalMs);
    };

    runCycle();

    return () => {
      stopped = true;
      if (cycleTimeout !== null) window.clearTimeout(cycleTimeout);
      controller?.abort();
      if (recorder && recorder.state !== 'inactive') {
        try {
          recorder.stop();
        } catch {
          // ignore
        }
      }
      recorder = null;
      // Stop and discard ONLY the cloned debug track; the main microphone track
      // is untouched.
      clonedTrack.stop();
    };
  }, [enabled, microphoneStream, audioIntervalMs]);

  // ---- Reset when disabled ------------------------------------------------
  useEffect(() => {
    if (enabled) return;
    setPyfeat(null);
    setOpensmile(null);
    setFrameProcessingMs(null);
    setSampleFps(null);
  }, [enabled]);

  return {pyfeat, opensmile, frameProcessingMs, sampleFps};
};
