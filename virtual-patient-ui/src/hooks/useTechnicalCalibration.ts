import {useCallback, useEffect, useRef, useState} from 'react';
import {selectVideoMimeType} from '../utils/mediaRecorder';

const TARGET_MS = 2_000;
const GAZE_INSTRUCTION_DELAY_MS = 15_000;
const CAMERA_MS = 3_000;
const VOICE_MS = 9_000;
const TARGETS = [
  ['CENTER', 0.5, 0.5], ['TOP_LEFT', 0.1, 0.1], ['BOTTOM_RIGHT', 0.9, 0.9],
  ['TOP_RIGHT', 0.9, 0.1], ['BOTTOM_LEFT', 0.1, 0.9], ['TOP_CENTER', 0.5, 0.1],
  ['BOTTOM_CENTER', 0.5, 0.9], ['MIDDLE_LEFT', 0.1, 0.5], ['MIDDLE_RIGHT', 0.9, 0.5],
] as const;

export type CalibrationStage = 'gaze' | 'camera' | 'voice';
export type CalibrationPhase = 'idle' | 'gaze_preparation' | 'gaze_targets' | 'camera_reference' | 'voice_baseline' | 'complete' | 'error';
type Geometry = {viewportWidth: number; viewportHeight: number; devicePixelRatio: number; screenWidth: number; screenHeight: number; orientation: 'portrait' | 'landscape'; videoWidth: number; videoHeight: number};
export type CalibrationCapture = {stage: CalibrationStage; blob: Blob; mimeType: string; durationMs: number; metadata: Record<string, unknown>};

const stageDuration = (stage: CalibrationStage) => stage === 'gaze' ? TARGETS.length * TARGET_MS : stage === 'camera' ? CAMERA_MS : VOICE_MS;
const readGeometry = (stream: MediaStream): Geometry => {
  const settings = stream.getVideoTracks()[0]?.getSettings();
  return {
    viewportWidth: window.innerWidth, viewportHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1, screenWidth: window.screen.width,
    screenHeight: window.screen.height, orientation: window.innerWidth >= window.innerHeight ? 'landscape' : 'portrait',
    videoWidth: settings?.width || 1, videoHeight: settings?.height || 1,
  };
};

export const useTechnicalCalibration = (microphoneStream: MediaStream | null, cameraStream: MediaStream | null) => {
  const [phase, setPhase] = useState<CalibrationPhase>('idle');
  const [remainingMs, setRemainingMs] = useState(0);
  const [activeTarget, setActiveTarget] = useState<{id: string; order: number; x: number; y: number} | null>(null);
  const [media, setMedia] = useState<CalibrationCapture | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const temporaryStreamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const animationRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const geometryStableRef = useRef(true);
  const sequenceRef = useRef(0);

  useEffect(() => {
    if (!microphoneStream?.active || typeof AudioContext === 'undefined') return undefined;
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(microphoneStream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const update = () => {
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
      setAudioLevel(Math.min(1, rms / 0.12));
      animationRef.current = requestAnimationFrame(update);
    };
    void context.resume();
    update();
    return () => {
 if (animationRef.current !== null) cancelAnimationFrame(animationRef.current); void context.close();
};
  }, [microphoneStream]);

  const stopTracks = useCallback(() => {
    temporaryStreamRef.current?.getTracks().forEach((track) => track.stop());
    temporaryStreamRef.current = null;
  }, []);
  const reset = useCallback(() => {
    sequenceRef.current += 1;
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    if (recorderRef.current?.state !== 'inactive') recorderRef.current?.stop();
    recorderRef.current = null;
    stopTracks();
    chunksRef.current = [];
    setPhase('idle'); setRemainingMs(0); setActiveTarget(null); setMedia(null);
  }, [stopTracks]);

  const start = useCallback(async (stage: CalibrationStage, stageMetadata: Record<string, unknown> = {}) => {
    const sequence = sequenceRef.current + 1;
    sequenceRef.current = sequence;
    if (stage === 'gaze') {
      const instructionStartedAt = performance.now();
      setPhase('gaze_preparation');
      setRemainingMs(GAZE_INSTRUCTION_DELAY_MS);
      timerRef.current = window.setInterval(() => {
        setRemainingMs(Math.max(0, GAZE_INSTRUCTION_DELAY_MS - (performance.now() - instructionStartedAt)));
      }, 50);
      await new Promise((resolve) => window.setTimeout(resolve, GAZE_INSTRUCTION_DELAY_MS));
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
      if (sequenceRef.current !== sequence) return;
    }
    const mimeType = selectVideoMimeType();
    if (!microphoneStream?.active || !cameraStream?.active || !mimeType) {
 setPhase('error'); return;
}
    const combined = new MediaStream([...microphoneStream.getAudioTracks().map((track) => track.clone()), ...cameraStream.getVideoTracks().map((track) => track.clone())]);
    let recorder: MediaRecorder;
    try {
 recorder = new MediaRecorder(combined, {mimeType});
} catch {
 combined.getTracks().forEach((track) => track.stop()); setPhase('error'); return;
}
    temporaryStreamRef.current = combined;
    recorderRef.current = recorder;
    chunksRef.current = [];
    const initial = readGeometry(cameraStream);
    geometryStableRef.current = true;
    const startedAt = performance.now();
    const duration = stageDuration(stage);
    const targets = TARGETS.map(([targetId, targetNormalizedX, targetNormalizedY], index) => ({
      targetId, targetOrder: index + 1, targetNormalizedX, targetNormalizedY,
      targetPixelX: targetNormalizedX * initial.viewportWidth, targetPixelY: targetNormalizedY * initial.viewportHeight,
      presentationStartMs: index * TARGET_MS, presentationEndMs: (index + 1) * TARGET_MS,
      observationWindowStartMs: index * TARGET_MS + 250, observationWindowEndMs: (index + 1) * TARGET_MS,
    }));
    const markGeometryChange = () => {
 geometryStableRef.current = false;
};
    recorder.ondataavailable = (event) => {
 if (event.data.size) chunksRef.current.push(event.data);
};
    recorder.onerror = () => {
 window.removeEventListener('resize', markGeometryChange); setPhase('error'); stopTracks();
};
    recorder.onstop = () => {
      window.removeEventListener('resize', markGeometryChange);
      const stable = geometryStableRef.current && JSON.stringify(initial) === JSON.stringify(readGeometry(cameraStream));
      const blob = new Blob(chunksRef.current, {type: mimeType});
      stopTracks();
      if (!blob.size) {
 setPhase('error'); return;
}
      setMedia({stage, blob, mimeType, durationMs: performance.now() - startedAt, metadata: stage === 'gaze' ? {geometry: initial, targets, geometryStable: stable} : stageMetadata});
      setPhase('complete');
    };
    window.addEventListener('resize', markGeometryChange);
    if (stage === 'gaze') {
      const firstTarget = TARGETS[0];
      setActiveTarget({id: firstTarget[0], order: 1, x: firstTarget[1], y: firstTarget[2]});
    }
    recorder.start(1_000);
    setMedia(null);
    setPhase(stage === 'gaze' ? 'gaze_targets' : stage === 'camera' ? 'camera_reference' : 'voice_baseline');
    setRemainingMs(duration);
    timerRef.current = window.setInterval(() => {
      const elapsed = performance.now() - startedAt;
      setRemainingMs(Math.max(0, duration - elapsed));
      if (stage === 'gaze') {
        const index = Math.min(8, Math.floor(elapsed / TARGET_MS));
        const target = TARGETS[index];
        setActiveTarget({id: target[0], order: index + 1, x: target[1], y: target[2]});
      }
      if (elapsed >= duration) {
        if (timerRef.current !== null) window.clearInterval(timerRef.current);
        timerRef.current = null;
        setActiveTarget(null);
        recorder.stop();
      }
    }, 50);
  }, [cameraStream, microphoneStream, stopTracks]);

  useEffect(() => () => reset(), [reset]);
  return {phase, remainingMs, activeTarget, media, audioLevel, start, reset};
};
