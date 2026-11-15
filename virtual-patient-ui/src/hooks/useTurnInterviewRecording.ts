import {useEffect, useRef, useState} from 'react';
import {InterviewCapture, type CaptureState} from '../recording/InterviewCapture';
import {subscribeTurnConnection} from '../services/recordings/turns';
import type {UseInterviewRecordingOptions} from './useInterviewRecording';
import {usePatientAudioRoute} from './usePatientAudioRoute';

/** React adapter for {@link InterviewCapture}: wires browser events and exposes its state. */
export const useTurnInterviewRecording = (options: UseInterviewRecordingOptions) => {
  const latest = useRef(options);
  latest.current = options;
  const [state, setState] = useState<CaptureState>({status: 'idle', syncPending: false, errorCode: null, captureId: null});
  const captureRef = useRef<InterviewCapture | null>(null);
  captureRef.current ??= new InterviewCapture(() => latest.current, setState, options.initialOffsetMs ?? 0);
  const capture = captureRef.current;
  const audio = usePatientAudioRoute();
  const armed = useRef(false);
  const {enabled, interviewId, cameraStream, microphoneStream} = options;

  useEffect(() => {
    capture.attach();
    return () => capture.dispose();
  }, [capture]);

  useEffect(() => {
    if (!enabled || !interviewId || !cameraStream || !microphoneStream || armed.current) return;
    armed.current = true;
    void capture.arm();
  }, [capture, enabled, interviewId, cameraStream, microphoneStream]);

  useEffect(() => {
    if (!enabled || !interviewId) return;
    const offline = () => capture.goOffline();
    const online = () => void capture.goOnline();
    window.addEventListener('offline', offline);
    window.addEventListener('online', online);
    const unsubscribe = subscribeTurnConnection(interviewId, (connected) => (connected ? online() : offline()));
    const timer = setInterval(() => capture.sampleRegion(), 200);
    return () => {
      window.removeEventListener('offline', offline);
      window.removeEventListener('online', online);
      clearInterval(timer);
      unsubscribe();
    };
  }, [capture, enabled, interviewId]);

  useEffect(() => {
    if (!enabled) return;
    const check = () => capture.checkEnvironment();
    const ended = () => capture.deviceEnded();
    const tracks = [...(cameraStream?.getVideoTracks() ?? []), ...(microphoneStream?.getAudioTracks() ?? [])];
    tracks.forEach((track) => track.addEventListener?.('ended', ended));
    check();
    window.addEventListener('resize', check);
    window.addEventListener('orientationchange', check);
    const timer = setInterval(check, 200);
    return () => {
      clearInterval(timer);
      window.removeEventListener('resize', check);
      window.removeEventListener('orientationchange', check);
      tracks.forEach((track) => track.removeEventListener?.('ended', ended));
    };
  }, [capture, enabled, cameraStream, microphoneStream]);

  const {status, syncPending, errorCode, captureId} = state;
  const isCapturing = status === 'recording' && !syncPending;
  const [api] = useState(() => ({
    retryStart: () => capture.arm(),
    attemptStorageRecovery: () => capture.attemptStorageRecovery(),
    canRestartWithCurrentGeometry: () => capture.canContinueWithCurrentSetup(),
    restartAfterCancel: () => capture.reopen(),
    pause: capture.pause.bind(capture),
    resume: capture.resume.bind(capture),
    elapsedAt: capture.elapsedAt,
    sealForEnding: () => capture.seal(),
    finalize: (preserveOnly?: boolean) => capture.finalize(preserveOnly),
    stopForRecovery: () => capture.stopForRecovery(),
    markSpeechStart: () => capture.markSpeechStart(),
    submitStudentTurn: capture.submitStudentTurn.bind(capture),
    returnFloorToStudent: () => capture.returnFloorToStudent(),
    prepareStudentTurn: capture.prepareStudentTurn.bind(capture),
    recordStudentTurn: capture.recordStudentTurn.bind(capture),
    preparePatientTurn: capture.preparePatientTurn.bind(capture),
    beginPatientTurn: capture.beginPatientTurn.bind(capture),
    endPatientTurn: capture.endPatientTurn.bind(capture),
  }));

  return {...api, ...audio, status, errorCode, syncPending, captureSegmentId: captureId,
    segmentId: isCapturing ? captureId : null, isCapturing,
    canResume: status === 'paused' && !capture.isBlocked, canRestart: capture.isSealed,
    canRetryStart: errorCode === 'capture-start-failed'};
};
