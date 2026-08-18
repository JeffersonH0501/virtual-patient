import {useCallback, useEffect, useRef, useState} from 'react';
import {createSpeechInputProvider, SpeechInputProvider, SpeechInputState} from '../speech';
import {SpeechTiming} from '../types/recording';

type UseHandsFreeSpeechOptions = {
  language: string;
  paused: boolean;
  disabled?: boolean;
  autoStart?: boolean;
  onUtterance: (text: string, timing?: SpeechTiming) => void | Promise<void>;
};

export const useHandsFreeSpeech = ({
  language,
  paused,
  disabled = false,
  autoStart = false,
  onUtterance,
}: UseHandsFreeSpeechOptions) => {
  const providerRef = useRef<SpeechInputProvider | null>(null);
  const onUtteranceRef = useRef(onUtterance);
  const bufferRef = useRef('');
  const debounceTimerRef = useRef<number | null>(null);
  const bufferTimingRef = useRef<SpeechTiming | null>(null);
  const queueRef = useRef(Promise.resolve());
  const autoStartAttemptedRef = useRef(false);
  const [isSupported, setIsSupported] = useState(true);
  const [isEnabled, setIsEnabled] = useState(false);
  const [state, setState] = useState<SpeechInputState>('idle');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [errorCode, setErrorCode] = useState<string | null>(null);

  useEffect(() => {
    onUtteranceRef.current = onUtterance;
  }, [onUtterance]);

  const flushBuffer = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    const text = bufferRef.current.trim();
    const timing = bufferTimingRef.current;
    bufferRef.current = '';
    bufferTimingRef.current = null;
    if (!text) return;
    queueRef.current = queueRef.current
      .then(() => onUtteranceRef.current(text, timing ?? undefined))
      .catch(() => setErrorCode('send-failed'));
  }, []);

  const scheduleFlush = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = window.setTimeout(flushBuffer, 1200);
  }, [flushBuffer]);

  useEffect(() => {
    let provider: SpeechInputProvider;
    try {
      provider = createSpeechInputProvider({
        onInterimTranscript: setInterimTranscript,
        onFinalTranscript: (text, timing) => {
          bufferRef.current = `${bufferRef.current} ${text}`.trim();
          if (timing) {
            bufferTimingRef.current = bufferTimingRef.current
              ? {
                  startedAt: Math.min(bufferTimingRef.current.startedAt, timing.startedAt),
                  endedAt: Math.max(bufferTimingRef.current.endedAt, timing.endedAt),
                }
              : timing;
          }
          setInterimTranscript('');
          scheduleFlush();
        },
        onStateChange: setState,
        onError: (nextErrorCode) => {
          setErrorCode(nextErrorCode);
          if (
            nextErrorCode === 'not-allowed' ||
            nextErrorCode === 'service-not-allowed' ||
            nextErrorCode === 'audio-capture'
          ) {
            setIsEnabled(false);
          }
        },
      });
    } catch {
      setIsSupported(false);
      setErrorCode('unsupported-provider');
      return;
    }

    providerRef.current = provider;
    setIsSupported(provider.isSupported);
    if (!provider.isSupported) setErrorCode('unsupported');
    if (isEnabled && !disabled) provider.start(language);

    return () => {
      provider.dispose();
      providerRef.current = null;
    };
  }, [disabled, isEnabled, language, scheduleFlush]);

  useEffect(() => {
    const provider = providerRef.current;
    if (!provider || !isEnabled || disabled) return;
    if (paused) provider.pause();
    else provider.resume();
  }, [disabled, isEnabled, paused]);

  useEffect(() => {
    if (!autoStart) {
      autoStartAttemptedRef.current = false;
      return;
    }
    if (disabled || !isSupported || autoStartAttemptedRef.current) return;
    autoStartAttemptedRef.current = true;
    setErrorCode(null);
    setIsEnabled(true);
  }, [autoStart, disabled, isSupported]);

  useEffect(
    () => () => {
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
      }
    },
    [],
  );

  const toggle = useCallback(() => {
    if (!isSupported || disabled) return;
    setErrorCode(null);
    if (isEnabled) {
      flushBuffer();
      providerRef.current?.stop();
      setIsEnabled(false);
      return;
    }
    setIsEnabled(true);
  }, [disabled, flushBuffer, isEnabled, isSupported]);

  return {
    isSupported,
    isEnabled,
    isListening: state === 'listening',
    isPaused: state === 'paused',
    interimTranscript,
    errorCode,
    toggle,
  };
};
