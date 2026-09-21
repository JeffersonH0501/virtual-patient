import {useCallback, useEffect, useRef, useState} from 'react';
import {selectVideoMimeType} from '../utils/mediaRecorder';

const VALIDATION_MS = 2_500;
const TARGET_MS = 2_000;
const CAMERA_MS = 3_000;
const VOICE_MS = 9_000;
export const CALIBRATION_DURATION_MS = VALIDATION_MS + 9 * TARGET_MS + CAMERA_MS + VOICE_MS;

const TARGETS = [
  ['CENTER', 0.5, 0.5],
  ['TOP_LEFT', 0.1, 0.1],
  ['BOTTOM_RIGHT', 0.9, 0.9],
  ['TOP_RIGHT', 0.9, 0.1],
  ['BOTTOM_LEFT', 0.1, 0.9],
  ['TOP_CENTER', 0.5, 0.1],
  ['BOTTOM_CENTER', 0.5, 0.9],
  ['MIDDLE_LEFT', 0.1, 0.5],
  ['MIDDLE_RIGHT', 0.9, 0.5],
] as const;

export type CalibrationPhase =
  | 'idle'
  | 'capture_validation'
  | 'gaze_targets'
  | 'camera_reference'
  | 'voice_baseline'
  | 'complete'
  | 'error';
type Geometry = {
  viewportWidth: number;
  viewportHeight: number;
  devicePixelRatio: number;
  screenWidth: number;
  screenHeight: number;
  orientation: 'portrait' | 'landscape';
  videoWidth: number;
  videoHeight: number;
};
export type CalibrationCapture = {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  metadata: Record<string, unknown>;
};

const readGeometry = (stream: MediaStream): Geometry => {
  const settings = stream.getVideoTracks()[0]?.getSettings();
  return {
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1,
    screenWidth: window.screen.width,
    screenHeight: window.screen.height,
    orientation: window.innerWidth >= window.innerHeight ? 'landscape' : 'portrait',
    videoWidth: settings?.width || 1,
    videoHeight: settings?.height || 1,
  };
};

export const useTechnicalCalibration = (
  microphoneStream: MediaStream | null,
  cameraStream: MediaStream | null,
) => {
  const [phase, setPhase] = useState<CalibrationPhase>('idle');
  const [remainingMs, setRemainingMs] = useState(CALIBRATION_DURATION_MS);
  const [activeTarget, setActiveTarget] = useState<{
    id: string;
    order: number;
    x: number;
    y: number;
  } | null>(null);
  const [media, setMedia] = useState<CalibrationCapture | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const temporaryStreamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const animationRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const geometryStableRef = useRef(true);
  const metadataRef = useRef<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (!microphoneStream?.active || typeof AudioContext === 'undefined') return undefined;
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(microphoneStream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const update = () => {
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(
        samples.reduce((sum, value) => sum + value * value, 0) / samples.length,
      );
      setAudioLevel(Math.min(1, rms / 0.12));
      animationRef.current = requestAnimationFrame(update);
    };
    void context.resume();
    update();
    return () => {
      if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
      void context.close();
    };
  }, [microphoneStream]);

  const stopTracks = useCallback(() => {
    temporaryStreamRef.current?.getTracks().forEach((track) => track.stop());
    temporaryStreamRef.current = null;
  }, []);
  const finish = useCallback(() => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    setRemainingMs(0);
    setActiveTarget(null);
    if (recorderRef.current?.state !== 'inactive') recorderRef.current?.stop();
  }, []);

  const start = useCallback(async () => {
    const mimeType = selectVideoMimeType();
    if (!microphoneStream?.active || !cameraStream?.active || !mimeType) {
      setPhase('error');
      return;
    }
    const combined = new MediaStream([
      ...microphoneStream.getAudioTracks().map((track) => track.clone()),
      ...cameraStream.getVideoTracks().map((track) => track.clone()),
    ]);
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(combined, {mimeType});
    } catch {
      combined.getTracks().forEach((track) => track.stop());
      setPhase('error');
      return;
    }
    temporaryStreamRef.current = combined;
    recorderRef.current = recorder;
    chunksRef.current = [];
    const initial = readGeometry(cameraStream);
    geometryStableRef.current = true;
    const startedAt = performance.now();
    startedAtRef.current = startedAt;
    const targets = TARGETS.map(([targetId, targetNormalizedX, targetNormalizedY], index) => {
      const presentationStartMs = VALIDATION_MS + index * TARGET_MS;
      return {
        targetId,
        targetOrder: index + 1,
        targetNormalizedX,
        targetNormalizedY,
        targetPixelX: targetNormalizedX * initial.viewportWidth,
        targetPixelY: targetNormalizedY * initial.viewportHeight,
        presentationStartMs,
        presentationEndMs: presentationStartMs + TARGET_MS,
        observationWindowStartMs: presentationStartMs + 250,
        observationWindowEndMs: presentationStartMs + TARGET_MS,
      };
    });
    metadataRef.current = {
      geometry: initial,
      targets,
      cameraReferenceStartMs: VALIDATION_MS + 9 * TARGET_MS,
      cameraReferenceEndMs: VALIDATION_MS + 9 * TARGET_MS + CAMERA_MS,
      voiceBaselineStartMs: VALIDATION_MS + 9 * TARGET_MS + CAMERA_MS,
      voiceBaselineEndMs: CALIBRATION_DURATION_MS,
      geometryStable: true,
    };
    const markGeometryChange = () => {
      geometryStableRef.current = false;
    };
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunksRef.current.push(event.data);
    };
    recorder.onerror = () => {
      window.removeEventListener('resize', markGeometryChange);
      setPhase('error');
      stopTracks();
    };
    recorder.onstop = () => {
      window.removeEventListener('resize', markGeometryChange);
      const stable =
        geometryStableRef.current &&
        JSON.stringify(initial) === JSON.stringify(readGeometry(cameraStream));
      const blob = new Blob(chunksRef.current, {type: mimeType});
      stopTracks();
      if (!blob.size) {
        setPhase('error');
        return;
      }
      setMedia({
        blob,
        mimeType,
        durationMs: performance.now() - startedAtRef.current,
        metadata: {...metadataRef.current, geometryStable: stable},
      });
      setPhase('complete');
    };
    window.addEventListener('resize', markGeometryChange);
    recorder.start(1_000);
    setMedia(null);
    setPhase('capture_validation');
    setRemainingMs(CALIBRATION_DURATION_MS);
    timerRef.current = window.setInterval(() => {
      const elapsed = performance.now() - startedAt;
      setRemainingMs(Math.max(0, CALIBRATION_DURATION_MS - elapsed));
      if (elapsed < VALIDATION_MS) {
        setPhase('capture_validation');
        setActiveTarget(null);
      } else if (elapsed < VALIDATION_MS + 9 * TARGET_MS) {
        const targetIndex = Math.min(8, Math.floor((elapsed - VALIDATION_MS) / TARGET_MS));
        const target = TARGETS[targetIndex];
        setPhase('gaze_targets');
        setActiveTarget({id: target[0], order: targetIndex + 1, x: target[1], y: target[2]});
      } else if (elapsed < VALIDATION_MS + 9 * TARGET_MS + CAMERA_MS) {
        setPhase('camera_reference');
        setActiveTarget(null);
      } else if (elapsed < CALIBRATION_DURATION_MS) {
        setPhase('voice_baseline');
        setActiveTarget(null);
      } else finish();
    }, 50);
  }, [cameraStream, finish, microphoneStream, stopTracks]);

  const reset = useCallback(() => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    if (recorderRef.current?.state !== 'inactive') recorderRef.current?.stop();
    recorderRef.current = null;
    stopTracks();
    chunksRef.current = [];
    setPhase('idle');
    setRemainingMs(CALIBRATION_DURATION_MS);
    setActiveTarget(null);
    setMedia(null);
  }, [stopTracks]);
  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      if (recorderRef.current?.state !== 'inactive') recorderRef.current?.stop();
      stopTracks();
    },
    [stopTracks],
  );
  return {phase, remainingMs, activeTarget, media, audioLevel, start, reset};
};
