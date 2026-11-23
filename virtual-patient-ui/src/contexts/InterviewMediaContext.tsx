import {FC, PropsWithChildren, useCallback, useEffect, useLayoutEffect, useRef, useState} from 'react';
import {InterviewMediaContext, MediaAccessState} from './interviewMedia';

const errorState = (error: unknown): MediaAccessState => {
  if (!(error instanceof DOMException)) return 'unavailable';
  return error.name === 'NotAllowedError' || error.name === 'SecurityError'
    ? 'permission-denied'
    : 'unavailable';
};

/** `capturing` is true only on calibration and session routes; elsewhere the camera and microphone are released. */
export const InterviewMediaProvider: FC<PropsWithChildren<{interviewId?: string; capturing: boolean}>> = ({
  children,
  interviewId,
  capturing,
}) => {
  const activeInterviewRef = useRef(interviewId);
  const cameraRef = useRef<MediaStream | null>(null);
  const microphoneRef = useRef<MediaStream | null>(null);
  const cameraDeviceRef = useRef('');
  const microphoneDeviceRef = useRef('');
  const cameraRequestRef = useRef<Promise<void> | null>(null);
  const microphoneRequestRef = useRef<Promise<void> | null>(null);
  const requestGenerationRef = useRef(0);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [microphoneStream, setMicrophoneStream] = useState<MediaStream | null>(null);
  const [cameraState, setCameraState] = useState<MediaAccessState>('idle');
  const [microphoneState, setMicrophoneState] = useState<MediaAccessState>('idle');
  const [cameraDeviceId, setCameraDeviceId] = useState('');
  const [microphoneDeviceId, setMicrophoneDeviceId] = useState('');

  const stopAll = useCallback(() => {
    requestGenerationRef.current += 1;
    cameraRef.current?.getTracks().forEach((track) => track.stop());
    microphoneRef.current?.getTracks().forEach((track) => track.stop());
    cameraRef.current = null;
    microphoneRef.current = null;
    cameraRequestRef.current = null;
    microphoneRequestRef.current = null;
    setCameraStream(null);
    setMicrophoneStream(null);
    setCameraState('idle');
    setMicrophoneState('idle');
  }, []);

  const startCamera = useCallback(async (deviceId = cameraDeviceRef.current) => {
    // Reuse an in-flight request only for the same device; a switch must proceed.
    if (cameraRequestRef.current && deviceId === cameraDeviceRef.current) return cameraRequestRef.current;
    if (deviceId !== cameraDeviceRef.current) {
      cameraDeviceRef.current = deviceId;
      setCameraDeviceId(deviceId);
      cameraRef.current?.getTracks().forEach((track) => track.stop());
      cameraRef.current = null;
      setCameraStream(null);
    }
    if (cameraRef.current?.active) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraState('unsupported');
      return;
    }
    setCameraState('loading');
    const generation = requestGenerationRef.current;
    const request = navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        ...(deviceId ? {deviceId: {exact: deviceId}} : {facingMode: 'user'}),
        width: {ideal: 1280},
        height: {ideal: 720},
        aspectRatio: {ideal: 16 / 9},
        frameRate: {ideal: 30, max: 30},
      },
    }).then((stream) => {
      if (generation !== requestGenerationRef.current || cameraRequestRef.current !== request) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      cameraRef.current = stream;
      setCameraStream(stream);
      setCameraState('ready');
      stream.getVideoTracks()[0]?.addEventListener('ended', () => {
        if (cameraRef.current !== stream) return;
        cameraRef.current = null;
        setCameraStream(null);
        setCameraState('unavailable');
      }, {once: true});
    }).catch((error: unknown) => {
      if (generation !== requestGenerationRef.current || cameraRequestRef.current !== request) return;
      setCameraState(errorState(error));
    }).finally(() => {
      if (cameraRequestRef.current === request) cameraRequestRef.current = null;
    });
    cameraRequestRef.current = request;
    return request;
  }, []);

  const startMicrophone = useCallback(async (deviceId = microphoneDeviceRef.current) => {
    // Reuse an in-flight request only for the same device; a switch must proceed.
    if (microphoneRequestRef.current && deviceId === microphoneDeviceRef.current) return microphoneRequestRef.current;
    if (deviceId !== microphoneDeviceRef.current) {
      microphoneDeviceRef.current = deviceId;
      setMicrophoneDeviceId(deviceId);
      microphoneRef.current?.getTracks().forEach((track) => track.stop());
      microphoneRef.current = null;
      setMicrophoneStream(null);
    }
    if (microphoneRef.current?.active) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicrophoneState('unsupported');
      return;
    }
    setMicrophoneState('loading');
    const generation = requestGenerationRef.current;
    const request = navigator.mediaDevices.getUserMedia({
      video: false,
      audio: {
        ...(deviceId ? {deviceId: {exact: deviceId}} : {}),
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      },
    }).then((stream) => {
      if (generation !== requestGenerationRef.current || microphoneRequestRef.current !== request) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      microphoneRef.current = stream;
      setMicrophoneStream(stream);
      setMicrophoneState('ready');
      stream.getAudioTracks()[0]?.addEventListener('ended', () => {
        if (microphoneRef.current !== stream) return;
        microphoneRef.current = null;
        setMicrophoneStream(null);
        setMicrophoneState('unavailable');
      }, {once: true});
    }).catch((error: unknown) => {
      if (generation !== requestGenerationRef.current || microphoneRequestRef.current !== request) return;
      setMicrophoneState(errorState(error));
    }).finally(() => {
      if (microphoneRequestRef.current === request) microphoneRequestRef.current = null;
    });
    microphoneRequestRef.current = request;
    return request;
  }, []);

  // Layout effects run before the passive effects of children, so a screen that mounts in the same navigation and
  // asks for the devices (resuming calibration leaves the session route of the same interview) is not invalidated
  // by the release that belongs to the previous route.
  useLayoutEffect(() => {
    if (activeInterviewRef.current !== interviewId) {
      stopAll();
      activeInterviewRef.current = interviewId;
    }
  }, [interviewId, stopAll]);

  useLayoutEffect(() => {
    if (!capturing) stopAll();
  }, [capturing, stopAll]);

  useEffect(() => () => stopAll(), [stopAll]);

  const bindInterview = useCallback((id: string) => {
    activeInterviewRef.current = id;
  }, []);

  return (
    <InterviewMediaContext.Provider value={{
      cameraStream,
      microphoneStream,
      cameraState,
      microphoneState,
      cameraDeviceId,
      microphoneDeviceId,
      startCamera,
      startMicrophone,
      stopAll,
      bindInterview,
    }}>
      {children}
    </InterviewMediaContext.Provider>
  );
};
