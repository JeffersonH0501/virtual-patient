import {useCallback, useEffect, useRef, useState} from 'react';

export const useLocalCamera = (autoStart = true) => {
  const streamRef = useRef<MediaStream | null>(null);
  const requestVersionRef = useRef(0);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [isEnabled, setIsEnabled] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const stop = useCallback(() => {
    requestVersionRef.current += 1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
    setIsEnabled(false);
    setIsStarting(false);
  }, []);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || streamRef.current) {
      if (!navigator.mediaDevices?.getUserMedia) setErrorCode('unsupported');
      return;
    }
    const requestVersion = ++requestVersionRef.current;
    setIsStarting(true);
    setErrorCode(null);
    try {
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: {ideal: 1280},
          height: {ideal: 720},
          aspectRatio: {ideal: 16 / 9},
          frameRate: {ideal: 30, max: 30},
        },
        audio: false,
      });
      if (requestVersion !== requestVersionRef.current) {
        nextStream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = nextStream;
      setStream(nextStream);
      setIsEnabled(true);
    } catch (error) {
      if (requestVersion !== requestVersionRef.current) return;
      const name = error instanceof DOMException ? error.name : 'unknown';
      setErrorCode(name === 'NotAllowedError' ? 'permission-denied' : 'unavailable');
      streamRef.current = null;
      setStream(null);
      setIsEnabled(false);
    } finally {
      if (requestVersion === requestVersionRef.current) setIsStarting(false);
    }
  }, [stop]);

  useEffect(() => {
    if (autoStart) void start();
    return stop;
  }, [autoStart, start, stop]);

  const toggle = useCallback(() => {
    if (isEnabled || isStarting) stop();
    else void start();
  }, [isEnabled, isStarting, start, stop]);

  return {stream, isEnabled, isStarting, errorCode, start, stop, toggle};
};
