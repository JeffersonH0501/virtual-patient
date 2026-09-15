import {useCallback, useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Message} from '../../types';
import {synthesizePatientMessage} from '../../services/speech';

type ConversationTranscriptProps = {
  interviewId: number;
  messages?: Message[];
  interimTranscript: string;
  isLoading: boolean;
  audioAutoPlayEnabled: boolean;
  playbackReady?: boolean;
  useAvatarSpeech?: boolean;
  onPatientSpeakingChange: (speaking: boolean) => void;
  captureEnabled?: boolean;
  routePatientAudio?: (audio: HTMLAudioElement) => boolean;
  onPatientTurnStart?: (messageId: number, sequence: number, transcript: string) => void;
  onPatientTurnEnd?: (messageId: number) => void;
};

export const ConversationTranscript = ({
  interviewId,
  messages,
  interimTranscript,
  isLoading,
  audioAutoPlayEnabled,
  playbackReady = true,
  useAvatarSpeech = false,
  onPatientSpeakingChange,
  captureEnabled = false,
  routePatientAudio,
  onPatientTurnStart,
  onPatientTurnEnd,
}: ConversationTranscriptProps) => {
  const {t, i18n} = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlsRef = useRef(new Map<number, string>());
  const autoPlayedRef = useRef(new Set<number>());
  const playingMessageRef = useRef<number | null>(null);
  const [playingMessageId, setPlayingMessageId] = useState<number | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);

  const stopAudio = useCallback(() => {
    const messageId = playingMessageRef.current;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    playingMessageRef.current = null;
    if (messageId !== null) onPatientTurnEnd?.(messageId);
    setPlayingMessageId(null);
    onPatientSpeakingChange(false);
  }, [onPatientSpeakingChange, onPatientTurnEnd]);

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
        stopAudio();
        return;
      }
      stopAudio();
      setAudioError(null);
      try {
        const sequence = messages?.findIndex((candidate) => candidate.id === message.id) ?? 0;
        if (useAvatarSpeech) {
          await onPatientTurnStart?.(message.id, Math.max(sequence, 0), message.content);
          onPatientTurnEnd?.(message.id);
          return;
        }
        const source = await getAudioSource(message);
        const audio = new Audio(source);
        audioRef.current = audio;
        const routed = routePatientAudio?.(audio) ?? false;
        if (captureEnabled && !routed && !audioAutoPlayEnabled) {
          audioRef.current = null;
          return;
        }
        audio.onplay = () => {
          playingMessageRef.current = message.id;
          setPlayingMessageId(message.id);
          onPatientSpeakingChange(true);
          onPatientTurnStart?.(message.id, Math.max(sequence, 0), message.content);
        };
        audio.onended = stopAudio;
        audio.onerror = () => {
          setAudioError(t('clinicalChat.call.audioUnavailable'));
          stopAudio();
        };
        await audio.play();
      } catch {
        setAudioError(t('clinicalChat.call.audioUnavailable'));
        stopAudio();
      }
    },
    [audioAutoPlayEnabled, captureEnabled, getAudioSource, messages, onPatientSpeakingChange, onPatientTurnEnd, onPatientTurnStart, playingMessageId, routePatientAudio, stopAudio, t, useAvatarSpeech],
  );

  useEffect(() => {
    containerRef.current?.scrollTo({
      top: containerRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [interimTranscript, isLoading, messages]);

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
        <h2 className="text-sm font-medium text-slate-600">
          {t('clinicalChat.call.transcript')}
        </h2>
      </header>
      <div
        ref={containerRef}
        className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 py-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:px-5 sm:py-4"
        aria-live="polite"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-3">
        {messages?.map((message) => {
          const isStudent = message.senderType === 'user';
          return (
            <article
              key={message.id}
              className={`rounded-xl border px-3 py-2.5 text-left ${
                isStudent
                  ? 'ml-5 border-blue-100 bg-blue-50 sm:ml-12'
                  : 'mr-5 border-slate-200 bg-slate-100 sm:mr-12'
              }`}
            >
              <div className="flex items-start gap-2">
                <p className="min-w-0 flex-1 whitespace-pre-wrap text-sm leading-5 text-slate-800">
                  {message.content}
                </p>
              </div>
              <div className="mt-1 flex justify-end text-[10px] leading-3 text-slate-400">
                <time dateTime={message.createdAt}>
                  {new Date(message.createdAt).toLocaleTimeString(timeLocale, {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </time>
              </div>
            </article>
          );
        })}
        {interimTranscript && (
          <article className="ml-5 rounded-xl border border-dashed border-blue-300 bg-blue-50/60 px-3 py-2.5 text-left sm:ml-12">
            <span className="text-[11px] font-medium text-blue-700">
              {t('clinicalChat.call.listeningNow')}
            </span>
            <p className="mt-1 text-sm leading-5 text-slate-600">{interimTranscript}</p>
          </article>
        )}
        {isLoading && (
          <div className="flex items-center gap-2 px-2 py-1 text-left text-xs text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
            {t('clinicalChat.call.patientThinking')}
          </div>
        )}
        {audioError && <p className="text-center text-xs text-amber-700">{audioError}</p>}
        </div>
      </div>
    </section>
  );
};
