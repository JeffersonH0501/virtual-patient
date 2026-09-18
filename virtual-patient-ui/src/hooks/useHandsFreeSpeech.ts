import {useCallback, useEffect, useRef, useState} from 'react';
import {createSpeechInputProvider, SpeechInputProvider, SpeechInputState} from '../speech';
import {SpeechTiming} from '../types/recording';

type UseHandsFreeSpeechOptions = {
  language: string;
  paused: boolean;
  disabled?: boolean;
  autoStart?: boolean;
  microphoneStream?: MediaStream | null;
  onUtteranceCommitted?: () => void;
  onSpeechStart?: () => void;
  onUtteranceFailed?: () => void;
  onUtterance: (text: string, timing?: SpeechTiming) => void | Promise<void>;
};

export const useHandsFreeSpeech = ({
  language,
  paused,
  disabled = false,
  autoStart = false,
  microphoneStream = null,
  onUtteranceCommitted,
  onSpeechStart,
  onUtteranceFailed,
  onUtterance,
}: UseHandsFreeSpeechOptions) => {
  const providerRef = useRef<SpeechInputProvider | null>(null);
  const onUtteranceRef = useRef(onUtterance);
  const bufferRef = useRef('');
  const debounceTimerRef = useRef<number | null>(null);
  const bufferTimingRef = useRef<SpeechTiming | null>(null);
  const queueRef = useRef(Promise.resolve());
  const autoStartAttemptedRef = useRef(false);
  const acceptingInputRef = useRef(!paused && !disabled);
  const awaitingCommittedTranscriptRef = useRef(false);
  const [isSupported, setIsSupported] = useState(true);
  const [isEnabled, setIsEnabled] = useState(false);
  const [state, setState] = useState<SpeechInputState>('idle');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [audioLevel, setAudioLevel] = useState(0);
  const [hasPendingUtterance, setHasPendingUtterance] = useState(false);
  const [isSubmittingUtterance, setIsSubmittingUtterance] = useState(false);

  acceptingInputRef.current = !paused && !disabled;

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
      .then(() => {
        const result = onUtteranceRef.current(text, timing ?? undefined);
        setIsSubmittingUtterance(false);
        return result;
      })
      .catch(() => setErrorCode('send-failed'));
  }, []);

  useEffect(() => {
    let provider: SpeechInputProvider;
    try {
      provider = createSpeechInputProvider({
        onInterimTranscript: (text) => {
          if (acceptingInputRef.current) {
            setInterimTranscript(text);
            if (text) setHasPendingUtterance(true);
          }
        },
        onUtteranceCaptured: () => {
          if (!acceptingInputRef.current) return;
          acceptingInputRef.current = false;
          awaitingCommittedTranscriptRef.current = true;
          setIsSubmittingUtterance(true);
          onUtteranceCommitted?.();
        },
        onSpeechStart,
        onFinalTranscript: (text, timing) => {
          if (!acceptingInputRef.current && !awaitingCommittedTranscriptRef.current) return;
          acceptingInputRef.current = false;
          awaitingCommittedTranscriptRef.current = false;
          setHasPendingUtterance(false);
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
          flushBuffer();
        },
        onStateChange: setState,
        onAudioLevel: setAudioLevel,
        onError: (nextErrorCode) => {
          setErrorCode(nextErrorCode);
          if (nextErrorCode === 'transcription-failed') {
            awaitingCommittedTranscriptRef.current = false;
            setHasPendingUtterance(false);
            setIsSubmittingUtterance(false);
            onUtteranceFailed?.();
          }
          if (
            nextErrorCode === 'not-allowed' ||
            nextErrorCode === 'service-not-allowed' ||
            nextErrorCode === 'audio-capture'
          ) {
            setIsEnabled(false);
          }
        },
      }, microphoneStream);
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
  }, [disabled, flushBuffer, isEnabled, language, microphoneStream, onSpeechStart, onUtteranceCommitted, onUtteranceFailed]);

  useEffect(() => {
    const provider = providerRef.current;
    if (!provider || !isEnabled || disabled) return;
    if (paused) {
      setInterimTranscript('');
      setAudioLevel(0);
      provider.pause();
    } else provider.resume();
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

  const submitUtterance = useCallback(() => {
    if (!hasPendingUtterance || paused || disabled) return;
    providerRef.current?.submitUtterance();
  }, [disabled, hasPendingUtterance, paused]);

  const stop = useCallback(() => {
    providerRef.current?.stop();
    setIsEnabled(false);
    setInterimTranscript('');
    setAudioLevel(0);
    setHasPendingUtterance(false);
    setIsSubmittingUtterance(false);
  }, []);

  return {
    isSupported,
    isEnabled,
    isListening: state === 'listening',
    isPaused: state === 'paused',
    interimTranscript,
    audioLevel,
    hasPendingUtterance,
    isSubmittingUtterance,
    errorCode,
    submitUtterance,
    stop,
    toggle,
  };
};
