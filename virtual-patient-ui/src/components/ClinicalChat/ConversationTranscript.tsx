import {CSSProperties, useCallback, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Message} from '../../types';
import {synthesizePatientMessage} from '../../services/speech';
import {PaperPlaneRight} from '../../icons';

type ConversationTranscriptProps = {
  interviewId: number;
  messages?: Message[];
  isListening: boolean;
  audioLevel: number;
  patientAudioLevel: number;
  hasPendingUtterance: boolean;
  isSubmittingUtterance: boolean;
  onSubmitUtterance: () => void;
  isLoading: boolean;
  audioAutoPlayEnabled: boolean;
  playbackReady?: boolean;
  onPatientSpeakingChange: (speaking: boolean) => void;
  captureEnabled?: boolean;
  routePatientAudio?: (audio: HTMLAudioElement) => boolean;
  onPatientTurnStart?: (messageId: number, sequence: number, transcript: string) => void;
  onPatientTurnEnd?: (messageId: number) => void;
  onPatientTurnComplete?: () => void;
};

export const ConversationTranscript = ({
  interviewId,
  messages,
  isListening,
  audioLevel,
  patientAudioLevel,
  hasPendingUtterance,
  isSubmittingUtterance,
  onSubmitUtterance,
  isLoading,
  audioAutoPlayEnabled,
  playbackReady = true,
  onPatientSpeakingChange,
  captureEnabled = false,
  routePatientAudio,
  onPatientTurnStart,
  onPatientTurnEnd,
  onPatientTurnComplete,
}: ConversationTranscriptProps) => {
  const {t, i18n} = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlsRef = useRef(new Map<number, string>());
  const autoPlayedRef = useRef(new Set<number>());
  const playingMessageRef = useRef<number | null>(null);
  const [playingMessageId, setPlayingMessageId] = useState<number | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [waveform, setWaveform] = useState<number[]>([]);
  const [patientWaveform, setPatientWaveform] = useState<number[]>([]);
  const [pendingPatientMessageId, setPendingPatientMessageId] = useState<number | null>(null);
  const revealedPatientMessagesRef = useRef(new Set<number>());
  const lastWaveSampleRef = useRef(0);
  const lastPatientWaveSampleRef = useRef(0);

  const stopAudio = useCallback((completeTurn = false) => {
    const messageId = playingMessageRef.current;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    playingMessageRef.current = null;
    if (messageId !== null) onPatientTurnEnd?.(messageId);
    setPlayingMessageId(null);
    if (completeTurn && messageId !== null) {
      revealedPatientMessagesRef.current.add(messageId);
      setPendingPatientMessageId(null);
      setPatientWaveform([]);
    }
    onPatientSpeakingChange(false);
    if (completeTurn) onPatientTurnComplete?.();
  }, [onPatientSpeakingChange, onPatientTurnComplete, onPatientTurnEnd]);

  const getAudioSource = useCallback(
    async (message: Message) => {
      const cachedUrl = objectUrlsRef.current.get(message.id);
      if (cachedUrl) return cachedUrl;
      const blob = await synthesizePatientMessage(interviewId, message.id);
      const objectUrl = URL.createObjectURL(blob);
      objectUrlsRef.current.set(message.id, objectUrl);
      return objectUrl;
    },
    [interviewId],
  );

  const playMessage = useCallback(
    async (message: Message) => {
      if (playingMessageId === message.id && audioRef.current) {
        stopAudio(false);
        return;
      }
      stopAudio(false);
      setPendingPatientMessageId(message.id);
      setPatientWaveform([]);
      setAudioError(null);
      try {
        const source = await getAudioSource(message);
        const audio = new Audio(source);
        audioRef.current = audio;
        const sequence = messages?.findIndex((candidate) => candidate.id === message.id) ?? 0;
        const routed = routePatientAudio?.(audio) ?? false;
        if (captureEnabled && !routed && !audioAutoPlayEnabled) {
          audioRef.current = null;
          revealedPatientMessagesRef.current.add(message.id);
          setPendingPatientMessageId(null);
          onPatientTurnComplete?.();
          return;
        }
        audio.onplay = () => {
          playingMessageRef.current = message.id;
          setPlayingMessageId(message.id);
          onPatientSpeakingChange(true);
          onPatientTurnStart?.(message.id, Math.max(sequence, 0), message.content);
        };
        audio.onended = () => stopAudio(true);
        audio.onerror = () => {
          setAudioError(t('clinicalChat.call.audioUnavailable'));
          stopAudio(true);
        };
        await audio.play();
      } catch {
        setAudioError(t('clinicalChat.call.audioUnavailable'));
        revealedPatientMessagesRef.current.add(message.id);
        setPendingPatientMessageId(null);
        stopAudio(true);
      }
    },
    [audioAutoPlayEnabled, captureEnabled, getAudioSource, messages, onPatientSpeakingChange, onPatientTurnComplete, onPatientTurnStart, playingMessageId, routePatientAudio, stopAudio, t],
  );

  useEffect(() => {
    if (!isListening && !isSubmittingUtterance) {
      setWaveform([]);
      return;
    }
    if (!isListening) return;
    const now = performance.now();
    if (now - lastWaveSampleRef.current < 120) return;
    lastWaveSampleRef.current = now;
    setWaveform((current) => [...current.slice(-79), Math.max(0.04, audioLevel)]);
  }, [audioLevel, isListening, isSubmittingUtterance]);

  useEffect(() => {
    if (playingMessageId === null) return;
    const now = performance.now();
    if (now - lastPatientWaveSampleRef.current < 120) return;
    lastPatientWaveSampleRef.current = now;
    setPatientWaveform((current) => [
      ...current.slice(-79),
      Math.max(0.04, patientAudioLevel),
    ]);
  }, [patientAudioLevel, playingMessageId]);

  useEffect(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return undefined;
    const scrollToBottom = () => {
      window.requestAnimationFrame(() => container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth',
      }));
    };
    scrollToBottom();
    const observer = new ResizeObserver(scrollToBottom);
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playbackReady) return;
    if ((!audioAutoPlayEnabled && !captureEnabled) || !messages) return;
    const newPatientMessage = [...messages]
      .reverse()
      .find(
        (message) =>
          message.senderType !== 'user' &&
          message.messageMetadata?.isNew &&
          !autoPlayedRef.current.has(message.id),
      );
    if (!newPatientMessage) return;
    autoPlayedRef.current.add(newPatientMessage.id);
    void playMessage(newPatientMessage);
  }, [audioAutoPlayEnabled, captureEnabled, messages, playMessage, playbackReady]);

  useEffect(
    () => () => {
      if (audioRef.current) audioRef.current.pause();
      objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
      onPatientSpeakingChange(false);
    },
    [onPatientSpeakingChange],
  );

  const timeLocale = i18n.resolvedLanguage?.startsWith('es') ? 'es-CO' : 'en-US';

  return (
    <section
      className="flex min-h-0 flex-1 flex-col"
      aria-label={t('clinicalChat.call.transcript')}
    >
      <header className="flex min-h-12 shrink-0 items-center border-b border-slate-200 bg-white px-4 text-left sm:px-5">
        <h2 className="component-title">
          {t('clinicalChat.call.transcript')}
        </h2>
      </header>
      <div
        ref={containerRef}
        className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-3 scrollbar-hidden sm:px-5 sm:py-4"
        aria-live="polite"
      >
        <div ref={contentRef} className="mx-auto flex w-full max-w-3xl flex-col gap-3 pb-1">
        {messages?.map((message) => {
          const isStudent = message.senderType === 'user';
          const hidePatientText = !isStudent
            && message.messageMetadata?.isNew
            && !revealedPatientMessagesRef.current.has(message.id);
          return (
            <article
              key={message.id}
              className={`transcript-bubble rounded-xl border px-3 py-2.5 text-left ${
                isStudent
                  ? 'ml-5 border-blue-100 bg-blue-50 sm:ml-12'
                  : 'mr-5 border-slate-200 bg-slate-100 sm:mr-12'
              }`}
            >
              {hidePatientText ? (
                <div className={`patient-voice-wave transition-opacity duration-300 ${pendingPatientMessageId === message.id ? 'opacity-100' : 'opacity-45'}`} aria-hidden="true">
                  {Array.from({length: 80}, (_, index) => {
                    const level = patientWaveform[index] ?? 0.025;
                    return (
                      <span
                        key={index}
                        data-wave-idle={patientWaveform[index] === undefined || undefined}
                        style={{'--wave-level': level} as CSSProperties}
                      />
                    );
                  })}
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <p className="min-w-0 flex-1 whitespace-pre-wrap text-sm leading-5 text-slate-800">
                    {message.content}
                  </p>
                </div>
              )}
              {!hidePatientText && <div className="mt-1 flex justify-end text-timestamp leading-3 text-slate-400">
                <time dateTime={message.createdAt}>
                  {new Date(message.createdAt).toLocaleTimeString(timeLocale, {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
              </div>}
            </article>
          );
        })}
        <div className={`grid transition-all duration-300 ease-out ${isListening || isSubmittingUtterance ? 'grid-rows-expanded opacity-100' : 'grid-rows-collapsed opacity-0'}`}>
          <div className="overflow-hidden">
            <article className="ml-5 rounded-xl border border-blue-100 bg-blue-50/70 px-3 py-2.5 text-left sm:ml-12">
              <div className="flex items-center gap-3">
                <div className="voice-wave" aria-hidden="true">
                  {Array.from({length: 80}, (_, index) => {
                    const level = waveform[index] ?? 0.025;
                    return (
                    <span
                      key={index}
                      data-wave-idle={waveform[index] === undefined || undefined}
                        style={{'--wave-level': level} as CSSProperties}
                    />
                    );
                  })}
                </div>
                <button
                  type="button"
                  onClick={onSubmitUtterance}
                  disabled={!hasPendingUtterance || isSubmittingUtterance}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 p-0 text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-200"
                  aria-label={t('clinicalChat.call.sendAudio')}
                  title={t('clinicalChat.call.sendAudio')}
                >
                  {isSubmittingUtterance ? (
                    <span className="h-5 w-5 animate-spin rounded-full border-spinner border-white/40 border-t-white" />
                  ) : (
                    <span className="block h-send-icon w-send-icon [&_svg]:h-full [&_svg]:w-full"><PaperPlaneRight color="currentColor" /></span>
                  )}
                </button>
              </div>
            </article>
          </div>
        </div>
        <div className={`grid transition-all duration-300 ease-out ${isLoading ? 'grid-rows-expanded opacity-100' : 'grid-rows-collapsed opacity-0'}`}>
          <div className="overflow-hidden">
            <div className="flex items-center gap-2 px-2 py-1 text-left text-xs text-slate-500">
              <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
              {t('clinicalChat.call.patientThinking')}
            </div>
          </div>
        </div>
        {audioError && <p className="text-center text-xs text-amber-700">{audioError}</p>}
        </div>
      </div>
    </section>
  );
};
