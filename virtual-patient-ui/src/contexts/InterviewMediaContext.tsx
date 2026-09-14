import {FC, PropsWithChildren, useCallback, useEffect, useRef, useState} from 'react';
import {InterviewMediaContext, MediaAccessState} from './interviewMedia';

const errorState = (error: unknown): MediaAccessState => {
  if (!(error instanceof DOMException)) return 'unavailable';
  return error.name === 'NotAllowedError' || error.name === 'SecurityError'
    ? 'permission-denied'
    : 'unavailable';
};

export const InterviewMediaProvider: FC<PropsWithChildren<{interviewId?: string}>> = ({
  children,
  interviewId,
}) => {
  const activeInterviewRef = useRef(interviewId);
  const cameraRef = useRef<MediaStream | null>(null);
  const microphoneRef = useRef<MediaStream | null>(null);
  const cameraRequestRef = useRef<Promise<void> | null>(null);
  const microphoneRequestRef = useRef<Promise<void> | null>(null);
  const requestGenerationRef = useRef(0);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [microphoneStream, setMicrophoneStream] = useState<MediaStream | null>(null);
  const [cameraState, setCameraState] = useState<MediaAccessState>('idle');
  const [microphoneState, setMicrophoneState] = useState<MediaAccessState>('idle');

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

  const startCamera = useCallback(async () => {
    if (cameraRef.current?.active) return;
    if (cameraRequestRef.current) return cameraRequestRef.current;
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraState('unsupported');
      return;
    }
    setCameraState('loading');
    const generation = requestGenerationRef.current;
    const request = navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: 'user',
        width: {ideal: 1280},
        height: {ideal: 720},
        aspectRatio: {ideal: 16 / 9},
        frameRate: {ideal: 30, max: 30},
      },
    }).then((stream) => {
      if (generation !== requestGenerationRef.current) {
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
      if (generation !== requestGenerationRef.current) return;
      setCameraState(errorState(error));
    }).finally(() => {
      if (cameraRequestRef.current === request) cameraRequestRef.current = null;
    });
    cameraRequestRef.current = request;
    return request;
  }, []);

  const startMicrophone = useCallback(async () => {
    if (microphoneRef.current?.active) return;
    if (microphoneRequestRef.current) return microphoneRequestRef.current;
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicrophoneState('unsupported');
      return;
    }
    setMicrophoneState('loading');
    const generation = requestGenerationRef.current;
    const request = navigator.mediaDevices.getUserMedia({
      video: false,
      audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
    }).then((stream) => {
      if (generation !== requestGenerationRef.current) {
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
      if (generation !== requestGenerationRef.current) return;
      setMicrophoneState(errorState(error));
    }).finally(() => {
      if (microphoneRequestRef.current === request) microphoneRequestRef.current = null;
    });
    microphoneRequestRef.current = request;
    return request;
  }, []);

  useEffect(() => {
    if (activeInterviewRef.current !== interviewId) {
      stopAll();
      activeInterviewRef.current = interviewId;
    }
  }, [interviewId, stopAll]);

  useEffect(() => () => stopAll(), [stopAll]);

  return (
    <InterviewMediaContext.Provider value={{
      cameraStream,
      microphoneStream,
      cameraState,
      microphoneState,
      startCamera,
      startMicrophone,
      stopAll,
    }}>
      {children}
    </InterviewMediaContext.Provider>
  );
};
