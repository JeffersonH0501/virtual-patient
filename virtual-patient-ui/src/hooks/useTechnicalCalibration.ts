import {useCallback, useEffect, useRef, useState} from 'react';
import {selectVideoMimeType} from '../utils/mediaRecorder';

const TARGET_MS = 4_000;
const GAZE_INSTRUCTION_DELAY_MS = 5_000;
const CAMERA_MS = 5_000;
const SETTLE_MS = 250;
const TARGETS = [
  ['CENTER', 0.5, 0.5], ['TOP_LEFT', 0.1, 0.1], ['BOTTOM_RIGHT', 0.9, 0.9],
  ['TOP_RIGHT', 0.9, 0.1], ['BOTTOM_LEFT', 0.1, 0.9],
] as const;

export type CalibrationStage = 'gaze' | 'camera' | 'unified' | 'guided';
export const GUIDED_CHECKS = [
  {kind: 'gaze_still', durationMs: 5000}, {kind: 'gaze_turn', durationMs: 6000},
  {kind: 'gaze_nod', durationMs: 6000}, {kind: 'gaze_away', durationMs: 5000},
  {kind: 'gaze_camera', durationMs: 5000}, {kind: 'nod_still', durationMs: 5000},
  {kind: 'nod_three', durationMs: 10000}, {kind: 'head_shake', durationMs: 8000},
  {kind: 'smile_neutral', durationMs: 5000}, {kind: 'smile_speech', durationMs: 8000},
  {kind: 'smile_silent', durationMs: 5000}, {kind: 'smile_speech_positive', durationMs: 8000},
] as const;
export type GuidedCheckKind = typeof GUIDED_CHECKS[number]['kind'];
export type GuidedCheckEnvironment = {
  deviceType: 'unspecified' | 'laptop' | 'tablet' | 'other';
  cameraPosition: 'unknown' | 'top' | 'bottom' | 'left' | 'right' | 'external';
};
export type CalibrationPhase = 'idle' | 'gaze_preparation' | 'gaze_targets' | 'camera_reference' | 'guided_check' | 'complete' | 'error';
type Geometry = {viewportWidth: number; viewportHeight: number; devicePixelRatio: number; screenWidth: number; screenHeight: number; orientation: 'portrait' | 'landscape'; videoWidth: number; videoHeight: number};
export type CalibrationCapture = {stage: CalibrationStage; blob: Blob; mimeType: string; durationMs: number; metadata: Record<string, unknown>};

export const readGeometry = (stream: MediaStream): Geometry => {
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
  const [activeCheck, setActiveCheck] = useState<GuidedCheckKind | null>(null);
  const [waitingForStep, setWaitingForStep] = useState(false);
  const waitingForStepRef = useRef(false);
  const startGuidedStepRef = useRef<(() => void) | null>(null);
  const [media, setMedia] = useState<CalibrationCapture | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const temporaryStreamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const animationRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const geometryStableRef = useRef(true);
  const sequenceRef = useRef(0);
  const cleanupRef = useRef<() => void>(() => undefined);
  const presentationRef = useRef<((order: number | null | GuidedCheckKind) => void) | null>(null);
  const [failureReason, setFailureReason] = useState<string | null>(null);

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
      if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
      void context.close();
    };
  }, [microphoneStream]);


  const reset = useCallback(() => {
    sequenceRef.current += 1;
    cleanupRef.current();
    cleanupRef.current = () => undefined;
    presentationRef.current = null;
    startGuidedStepRef.current = null;
    waitingForStepRef.current = false;
    setWaitingForStep(false);
    recorderRef.current = null;
    temporaryStreamRef.current = null;
    chunksRef.current = [];
    setFailureReason(null);
    setPhase('idle'); setRemainingMs(0); setActiveTarget(null); setActiveCheck(null); setMedia(null);
  }, []);

  const cancel = useCallback((reason = 'capture_interrupted') => {
    reset();
    setFailureReason(reason);
    setPhase('error');
  }, [reset]);
  const confirmPresentation = useCallback((order: number | null | GuidedCheckKind) => presentationRef.current?.(order), []);
  const startGuidedStep = useCallback(() => startGuidedStepRef.current?.(), []);

  const start = useCallback(async (stage: CalibrationStage, stageMetadata: Record<string, unknown> = {}) => {
    reset();
    const sequence = sequenceRef.current;
    const checks = stageMetadata.nonverbalOnly ? GUIDED_CHECKS.filter((item) => !item.kind.startsWith('gaze_')) : GUIDED_CHECKS;
    if (stage !== 'camera' && stage !== 'guided') {
      const instructionStartedAt = performance.now();
      setPhase('gaze_preparation');
      setRemainingMs(GAZE_INSTRUCTION_DELAY_MS);
      await new Promise<void>((resolve) => {
        const interval = window.setInterval(() => setRemainingMs(Math.max(0, GAZE_INSTRUCTION_DELAY_MS - (performance.now() - instructionStartedAt))), 50);
        const timeout = window.setTimeout(resolve, GAZE_INSTRUCTION_DELAY_MS);
        cleanupRef.current = () => { clearInterval(interval); clearTimeout(timeout); resolve(); };
      });
      if (sequenceRef.current !== sequence) return;
      cleanupRef.current();
    }
    const mimeType = selectVideoMimeType();
    if (!microphoneStream?.active || !cameraStream?.active || !mimeType) { cancel('recording_failed'); return; }
    const combined = new MediaStream([...microphoneStream.getAudioTracks().map((track) => track.clone()), ...cameraStream.getVideoTracks().map((track) => track.clone())]);
    temporaryStreamRef.current = combined;
    let recorder: MediaRecorder;
    try { recorder = new MediaRecorder(combined, {mimeType, videoBitsPerSecond: 2_500_000, audioBitsPerSecond: 96_000}); }
    catch { combined.getTracks().forEach((track) => track.stop()); cancel('recording_failed'); return; }
    recorderRef.current = recorder;
    const initial = readGeometry(cameraStream);
    geometryStableRef.current = true;
    const targets: Array<{targetId: string; targetOrder: number; targetNormalizedX: number; targetNormalizedY: number; targetPixelX: number; targetPixelY: number; presentationStartMs: number; presentationEndMs: number; observationWindowStartMs: number; observationWindowEndMs: number}> = [];
    let origin = 0;
    let pausedAt: number | null = null;
    let pausedMs = 0;
    let presentedAt: number | null = null;
    let targetIndex = stage === 'camera' ? TARGETS.length : 0;
    let pending = true;
    let cameraStart = 0;
    let guidedIndex = -1;
    const guidedChecks: {kind: GuidedCheckKind; startMs: number; observationStartMs: number; endMs: number}[] = [];
    let endedAt: number | null = null;
    let frameRequest: number | null = null;
    const elapsed = () => Math.round((pausedAt ?? performance.now()) - origin - pausedMs);
    const closeTarget = (time: number) => {
      const previous = targets[targets.length - 1];
      if (previous && previous.presentationEndMs === 0) { previous.presentationEndMs = time; previous.observationWindowEndMs = time; }
    };
    const showTarget = () => {
      const [id, x, y] = TARGETS[targetIndex];
      setActiveTarget({id, order: targetIndex + 1, x, y});
    };
    const waitForGuidedStep = () => {
      try {
        pausedAt = performance.now();
        recorder.pause();
      } catch {
        cancel('recording_failed');
        return;
      }
      pending = true;
      presentedAt = null;
      waitingForStepRef.current = true;
      setWaitingForStep(true);
      setActiveCheck(checks[guidedIndex].kind);
      setRemainingMs(checks[guidedIndex].durationMs);
      setPhase('guided_check');
    };
    startGuidedStepRef.current = () => {
      if (sequenceRef.current !== sequence || guidedIndex < 0 || !waitingForStepRef.current) return;
      try {
        const resumedAt = performance.now();
        recorder.resume();
        pausedMs += resumedAt - (pausedAt ?? resumedAt);
        pausedAt = null;
      } catch {
        cancel('recording_failed');
        return;
      }
      waitingForStepRef.current = false;
      setWaitingForStep(false);
      presentationRef.current?.(checks[guidedIndex].kind);
    };
    const markGeometryChange = () => { geometryStableRef.current = false; };
    cleanupRef.current = () => {
      if (timerRef.current !== null) clearInterval(timerRef.current);
      timerRef.current = null;
      if (frameRequest !== null) cancelAnimationFrame(frameRequest);
      window.removeEventListener('resize', markGeometryChange);
      document.removeEventListener('visibilitychange', markGeometryChange);
      recorder.onstart = null; recorder.onstop = null; recorder.ondataavailable = null; recorder.onerror = null;
      if (recorder.state !== 'inactive') recorder.stop();
      combined.getTracks().forEach((track) => track.stop());
    };
    presentationRef.current = (order) => {
      if (guidedIndex >= 0) {
        if (waitingForStepRef.current) return;
        if (sequenceRef.current !== sequence || !pending || order !== checks[guidedIndex].kind) return;
        const time = elapsed();
        guidedChecks.push({kind: checks[guidedIndex].kind, startMs: time, observationStartMs: time + SETTLE_MS, endMs: 0});
        presentedAt = performance.now(); pending = false;
        return;
      }
      if (sequenceRef.current !== sequence || !pending || (targetIndex < TARGETS.length ? order !== targetIndex + 1 : order !== null)) return;
      const time = elapsed();
      closeTarget(time);
      presentedAt = performance.now();
      pending = false;
      if (typeof order === 'number') {
        const [targetId, x, y] = TARGETS[targetIndex];
        targets.push({targetId, targetOrder: order, targetNormalizedX: x, targetNormalizedY: y, targetPixelX: x * initial.viewportWidth, targetPixelY: y * initial.viewportHeight, presentationStartMs: time, presentationEndMs: 0, observationWindowStartMs: time + SETTLE_MS, observationWindowEndMs: 0});
      } else cameraStart = time + SETTLE_MS;
    };
    recorder.ondataavailable = (event) => { if (sequenceRef.current === sequence && event.data.size) chunksRef.current.push(event.data); };
    recorder.onerror = () => { if (sequenceRef.current === sequence) cancel('recording_failed'); };
    recorder.onstop = () => {
      if (sequenceRef.current !== sequence) return;
      if (endedAt === null) { cancel('recording_failed'); return; }
      const durationMs = endedAt;
      closeTarget(durationMs);
      const blob = new Blob(chunksRef.current, {type: mimeType});
      const stable = geometryStableRef.current && JSON.stringify(initial) === JSON.stringify(readGeometry(cameraStream));
      cleanupRef.current(); cleanupRef.current = () => undefined; presentationRef.current = null;
      if (!blob.size) { cancel('recording_failed'); return; }
      setMedia({stage, blob, mimeType, durationMs, metadata: stage === 'guided'
        ? {geometry: initial, geometryStable: stable, guidedChecks, guidedEnvironment: stageMetadata.guidedEnvironment, attestations: stageMetadata.attestations}
        : stage !== 'camera'
        ? {geometry: initial, targets, gazeSource:'mediapipe_five_point_v1', geometryStable: stable, ...(stage === 'unified' ? {cameraReferenceStartMs: cameraStart, cameraReferenceEndMs: durationMs} : {})}
        : {...stageMetadata, geometry: initial, geometryStable: stable && JSON.stringify(initial) === JSON.stringify(stageMetadata.expectedGeometry)}});
      setPhase('complete');
    };
    recorder.onstart = () => {
      if (sequenceRef.current !== sequence) return;
      origin = performance.now();
      let lastFrame = origin;
      const watchFrames = () => {
        if (sequenceRef.current !== sequence) return;
        const now = performance.now();
        if (pausedAt === null && now - lastFrame > SETTLE_MS) { cancel('timing_unstable'); return; }
        lastFrame = now;
        frameRequest = requestAnimationFrame(watchFrames);
      };
      frameRequest = requestAnimationFrame(watchFrames);
      window.addEventListener('resize', markGeometryChange);
      document.addEventListener('visibilitychange', markGeometryChange);
      if (stage === 'guided') {
        guidedIndex = 0;
        waitForGuidedStep();
      }
      else setPhase(stage === 'camera' ? 'camera_reference' : 'gaze_targets');
      if (stage !== 'guided') setRemainingMs(stage === 'camera' ? CAMERA_MS : TARGET_MS);
      if (stage !== 'camera' && stage !== 'guided') showTarget();
      timerRef.current = window.setInterval(() => {
        if (sequenceRef.current !== sequence || presentedAt === null || pending) return;
        const duration = guidedIndex >= 0 ? checks[guidedIndex].durationMs : targetIndex < TARGETS.length ? TARGET_MS : CAMERA_MS;
        const remaining = Math.max(0, duration - (performance.now() - presentedAt));
        setRemainingMs(remaining);
        if (remaining > 0) return;
        if (guidedIndex >= 0) {
          guidedChecks[guidedChecks.length - 1].endMs = elapsed();
          if (guidedIndex < checks.length - 1) {
            guidedIndex += 1; waitForGuidedStep();
          } else {
            endedAt = elapsed(); clearInterval(timerRef.current!); timerRef.current = null; setActiveCheck(null); recorder.stop();
          }
        } else if (targetIndex < TARGETS.length - 1) { targetIndex += 1; pending = true; showTarget(); }
        else if (targetIndex === TARGETS.length - 1 && stage === 'unified') {
          targetIndex += 1; pending = true; setActiveTarget(null); setPhase('camera_reference'); setRemainingMs(CAMERA_MS);
        } else {
          endedAt = elapsed(); clearInterval(timerRef.current!); timerRef.current = null; setActiveTarget(null); recorder.stop();
        }
      }, 50);
    };
    try { recorder.start(1000); } catch { cancel('recording_failed'); }
  }, [cameraStream, microphoneStream, cancel, reset]);

  useEffect(() => () => reset(), [reset]);
  return {phase, remainingMs, activeTarget, activeCheck, waitingForStep, startGuidedStep, media, audioLevel, failureReason, start, reset, cancel, confirmPresentation};
};
