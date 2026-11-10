import {ReactNode, useCallback, useEffect, useId, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Message} from '../../types';
import {loadPatientSpeechBlob, patientSpeechUrl} from '../../services/speech/patientSpeechUrl';
import {LoaderCircle, SendHorizontal} from 'lucide-react';
import {MotionMessage} from '../common/Motion';
import {VoiceWave} from '../common/VoiceWave';
import {formatPlaybackTime} from '../../utils/duration';

type ConversationTranscriptProps = {
  capturePaused?: boolean;
  interviewId: number;
  headerAction?: ReactNode;
  startedAt?: number;
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
  routePatientAudio?: (audio: HTMLAudioElement) => boolean | Promise<boolean>;
  onPatientTurnStart?: (messageId: number, sequence: number, transcript: string) => void;
  onPatientTurnEnd?: (messageId: number, playbackComplete: boolean) => void;
  onPatientTurnComplete?: (messageId: number, delivery?: 'played' | 'written') => void;
  loadPatientAudio?: (message: Message, signal: AbortSignal) => Promise<string>;
  preparedAudio?: HTMLAudioElement | null;
  resumeAudioGraph?: (prepare?: boolean) => Promise<void>;
};

export const ConversationTranscript = ({
  interviewId,
  headerAction,
  startedAt,
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
  loadPatientAudio,
  preparedAudio,
  resumeAudioGraph,
  capturePaused = false,
}: ConversationTranscriptProps) => {
  const {t} = useTranslation();
  const sendAudioHintId = useId();
  const [hasSubmittedAudio, setHasSubmittedAudio] = useState(false);
  const showSendAudioHint = playbackReady && !hasSubmittedAudio && !messages?.some((message) => message.senderType === 'user');
  const messageIds = useRef(new Set(messages?.map((message) => message.id)));
  const messageBaseline = useRef(Boolean(messages?.length));
  useEffect(() => {
    if (!messages?.length) return;
    messages.forEach((message) => messageIds.current.add(message.id));
    messageBaseline.current = true;
  }, [messages]);
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const sendAudioRef = useRef<HTMLButtonElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blockedPlaybackRef = useRef<(() => void) | null>(null);
  const audioRequestRef = useRef<AbortController | null>(null);
  const audioObjectUrlRef = useRef<string | null>(null);
  const audioTimeoutRef = useRef<number | undefined>(undefined);
  const releaseAudio = useCallback(() => {
    blockedPlaybackRef.current = null;
    window.clearTimeout(audioTimeoutRef.current);
    audioRequestRef.current?.abort();
    audioRequestRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute('src');
      audioRef.current.load();
      audioRef.current = null;
    }
    if (audioObjectUrlRef.current) {
      URL.revokeObjectURL(audioObjectUrlRef.current);
      audioObjectUrlRef.current = null;
    }
  }, []);
  const autoPlayedRef = useRef(new Set<number>());
  const playingMessageRef = useRef<number | null>(null);
  const pausedPlaybackRef = useRef<HTMLAudioElement | null>(null);
  const restartAudioTimeoutRef = useRef<(() => void) | null>(null);
  const wasCapturePausedRef = useRef(false);
  const capturePausedRef = useRef(capturePaused);
  capturePausedRef.current = capturePaused;
  const [playingMessageId, setPlayingMessageId] = useState<number | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [failedPatientMessage, setFailedPatientMessage] = useState<Message | null>(null);
  const [pendingPatientMessageId, setPendingPatientMessageId] = useState<number | null>(null);
  const nextPatientMessage = messages?.slice().reverse().find((message) =>
    message.senderType !== 'user' && message.messageMetadata?.isNew);
  const playbackGenerationRef = useRef(0);
  const queuedPatientMessage = (audioAutoPlayEnabled || captureEnabled) && nextPatientMessage && !autoPlayedRef.current.has(nextPatientMessage.id);
  const waitingForPatient = playingMessageId === null && (isLoading || pendingPatientMessageId !== null || Boolean(queuedPatientMessage));
  const showStudentWave =
    playbackReady && !capturePaused && !isLoading && playingMessageId === null && !waitingForPatient && pendingPatientMessageId === null && !audioError && (isListening || isSubmittingUtterance);

  useEffect(() => {
    const handleSendShortcut = (event: KeyboardEvent) => {
      if (event.key !== 'Enter' || event.defaultPrevented || event.repeat || event.isComposing ||
          event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const button = sendAudioRef.current;
      if (!button || button.disabled || document.querySelector('[data-modal-open="true"], dialog[open]')) return;
      if (event.target instanceof Element && event.target.closest(
        'button, a[href], input, textarea, select, [contenteditable], [tabindex]',
      )) return;
      event.preventDefault();
      button.click();
    };
    document.addEventListener('keydown', handleSendShortcut);
    return () => document.removeEventListener('keydown', handleSendShortcut);
  }, []);

  const stopAudio = useCallback((completedMessageId?: number, written = false) => {
    restartAudioTimeoutRef.current = null;
    playbackGenerationRef.current += 1;
    const messageId = playingMessageRef.current;
    const playbackComplete = completedMessageId !== undefined && Boolean(audioRef.current?.ended);
    releaseAudio();
    playingMessageRef.current = null;
    if (messageId !== null) onPatientTurnEnd?.(messageId, playbackComplete);
    setPlayingMessageId(null);
    setPendingPatientMessageId(null);
    onPatientSpeakingChange(false);
    if (completedMessageId !== undefined && (playbackComplete || written)) {
      onPatientTurnComplete?.(completedMessageId, written ? 'written' : 'played');
    }
  }, [onPatientSpeakingChange, onPatientTurnComplete, onPatientTurnEnd, releaseAudio]);

  useEffect(() => {
    const audio = audioRef.current;
    const resuming = !capturePaused && wasCapturePausedRef.current;
    wasCapturePausedRef.current = capturePaused;
    if (capturePaused) {
      window.clearTimeout(audioTimeoutRef.current);
      if (audio) {
        pausedPlaybackRef.current = audio;
        audio.pause();
      }
    } else if (resuming) {
      restartAudioTimeoutRef.current?.();
    }
    if (resuming && audio && pausedPlaybackRef.current === audio) {
      pausedPlaybackRef.current = null;
      void audio.play().catch(() => {
        setAudioError(t('clinicalChat.call.audioUnavailable'));
        setFailedPatientMessage(messages?.find((message) => message.id === playingMessageRef.current) ?? null);
        stopAudio();
      });
    }
  }, [capturePaused, messages, stopAudio, t]);

  const playMessage = useCallback(
    async (message: Message) => {
      if (playingMessageId === message.id && audioRef.current) {
        stopAudio();
        return;
      }
      stopAudio();
      const generation = playbackGenerationRef.current;
      setPendingPatientMessageId(message.id);
      setAudioError(null);
      setFailedPatientMessage(null);
      const failPlayback = () => {
        if (generation !== playbackGenerationRef.current) return;
        setAudioError(t('clinicalChat.call.audioUnavailable'));
        setFailedPatientMessage(message);
        stopAudio(message.id);
      };
      const resetAudioTimeout = () => {
        window.clearTimeout(audioTimeoutRef.current);
        if (capturePausedRef.current) return;
        audioTimeoutRef.current = window.setTimeout(failPlayback, 20_000);
      };
      restartAudioTimeoutRef.current = resetAudioTimeout;
      resetAudioTimeout();
      try {
        let source: string;
        if (loadPatientAudio || preparedAudio) {
          const request = new AbortController();
          audioRequestRef.current = request;
          source = loadPatientAudio
            ? await loadPatientAudio(message, request.signal)
            : await loadPatientSpeechBlob(interviewId, message.id, request.signal);
          if (generation !== playbackGenerationRef.current) {
            URL.revokeObjectURL(source);
            return;
          }
          audioObjectUrlRef.current = source;
        } else {
          source = patientSpeechUrl(interviewId, message.id);
        }
        const audio = preparedAudio ?? new Audio();
        if (!preparedAudio) audio.crossOrigin = 'use-credentials';
        audioRef.current = audio;
        const sequence = messages?.findIndex((candidate) => candidate.id === message.id) ?? 0;
        audio.src = source;
        const routing = routePatientAudio?.(audio) ?? false;
        const routed = typeof routing === 'boolean' ? routing : await routing;
        if (generation !== playbackGenerationRef.current) return;
        if (captureEnabled && !routed && !audioAutoPlayEnabled) {
          stopAudio(message.id);
          return;
        }
        audio.onplaying = () => {
          if (generation !== playbackGenerationRef.current) {
            audio.pause();
            return;
          }
          if (playingMessageRef.current === message.id) return;
          playingMessageRef.current = message.id;
          setPlayingMessageId(message.id);
          onPatientSpeakingChange(true);
          onPatientTurnStart?.(message.id, Math.max(sequence, 0), message.content);
        };
        audio.onended = () => {
          if (generation === playbackGenerationRef.current) stopAudio(message.id);
        };
        audio.onerror = failPlayback;
        audio.ontimeupdate = () => {
          if (generation === playbackGenerationRef.current) resetAudioTimeout();
        };
        const play = async () => {
          try {
            if (capturePausedRef.current) {
              pausedPlaybackRef.current = audio;
              return;
            }
            if (resumeAudioGraph) await resumeAudioGraph();
            await audio.play();
          } catch (error) {
            if (generation !== playbackGenerationRef.current) return;
            if (!error || typeof error !== 'object' || !('name' in error) || error.name !== 'NotAllowedError') {
              failPlayback();
              return;
            }
            window.clearTimeout(audioTimeoutRef.current);
            setPendingPatientMessageId(null);
            setAudioError(t('clinicalChat.call.audioPlaybackBlocked'));
            setFailedPatientMessage(message);
            blockedPlaybackRef.current = () => {
              setAudioError(null);
              setFailedPatientMessage(null);
              setPendingPatientMessageId(message.id);
              resetAudioTimeout();
              void play();
            };
          }
        };
        await play();
      } catch {
        failPlayback();
      }
    },
    [audioAutoPlayEnabled, captureEnabled, interviewId, loadPatientAudio, messages, onPatientSpeakingChange, onPatientTurnStart, playingMessageId, preparedAudio, resumeAudioGraph, routePatientAudio, stopAudio, t],
  );

  useEffect(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return undefined;
    let frame = 0;
    const scrollToBottom = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    };
    scrollToBottom();
    const observer = new ResizeObserver(scrollToBottom);
    observer.observe(content);
    observer.observe(container);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, []);

  useEffect(() => {
    if (!playbackReady) return;
    if ((!audioAutoPlayEnabled && !captureEnabled) || !messages) return;
    if (!nextPatientMessage || autoPlayedRef.current.has(nextPatientMessage.id)) return;
    autoPlayedRef.current.add(nextPatientMessage.id);
    void playMessage(nextPatientMessage);
  }, [audioAutoPlayEnabled, captureEnabled, messages, nextPatientMessage, playMessage, playbackReady]);

  useEffect(
    () => () => {
      playbackGenerationRef.current += 1;
      releaseAudio();
      autoPlayedRef.current.clear();
      onPatientSpeakingChange(false);
    },
    [onPatientSpeakingChange, releaseAudio],
  );


  return (
    <section
      className="flex min-h-0 flex-1 flex-col"
      aria-label={t('clinicalChat.call.interview')}
    >
      <header className="ui-panel-header flex shrink-0 items-center justify-between gap-inset text-left">
        <h2 className="default-title">
          {t('clinicalChat.call.interview')}
        </h2>
        {headerAction}
      </header>
      <div
        ref={containerRef}
        className="ui-panel-body min-h-0 flex-1 overflow-x-hidden overflow-y-auto scrollbar-hidden"
        aria-live="polite"
      >
        <div ref={contentRef} className="mx-auto flex w-full max-w-3xl flex-col gap-layout pb-inset">
        {messages?.map((message, position) => {
          const isStudent = message.senderType === 'user';
          const elapsed = startedAt === undefined ? NaN : (Date.parse(message.createdAt) - startedAt) / 1000;
          const showPatientWave = !isStudent && playingMessageId === message.id;
          const preparingPatientAudio = !isStudent && !showPatientWave && (
            pendingPatientMessageId === message.id ||
            ((audioAutoPlayEnabled || captureEnabled) && nextPatientMessage?.id === message.id && !autoPlayedRef.current.has(message.id))
          );
          if (preparingPatientAudio) return null;
          return (
            <MotionMessage
              key={`${message.senderType}-${position}`}
              aria-busy={pendingPatientMessageId === message.id && playingMessageId !== message.id || undefined}
              newMessage={messageBaseline.current && !messageIds.current.has(message.id)}
              className={`transcript-bubble recap-turn-bubble ${
                isStudent ? 'recap-turn-bubble--student self-end' : 'self-start'
              } ${showPatientWave ? 'transcript-voice-bubble' : ''}`}
            >
              {showPatientWave ? (
                <>
                  <VoiceWave speaker="patient" level={patientAudioLevel} active={!capturePaused && playingMessageId === message.id} />
                </>
              ) : (
                <>
                  <span className="whitespace-pre-wrap text-neutral-800 default-text">{message.content}</span>
                  {Number.isFinite(elapsed) && <span className="recap-turn-meta text-neutral-500 secondary-text">
                    {formatPlaybackTime(elapsed)}
                  </span>}
                </>
              )}
            </MotionMessage>
          );
        })}
        <div className={showSendAudioHint && showStudentWave ? 'call-send-guide' : undefined}>
        <div hidden={!showStudentWave} inert={!showStudentWave}>
          <div className="min-h-0 overflow-hidden">
            <article className="recap-turn-bubble recap-turn-bubble--student transcript-voice-bubble ml-auto">
              <div className="flex items-center gap-layout">
                {showStudentWave && <VoiceWave speaker="student" level={audioLevel} active={isListening && !isSubmittingUtterance} />}
                <button
                  ref={sendAudioRef}
                  type="button"
                  onClick={() => {
                    onSubmitUtterance();
                    setHasSubmittedAudio(true);
                  }}
                  aria-keyshortcuts="Enter"
                  disabled={!showStudentWave || !hasPendingUtterance || isSubmittingUtterance}
                  className={`ui-icon-button ui-icon-button--brand ui-icon-button--large call-send-audio ${showSendAudioHint ? 'call-send-audio--highlighted' : ''}`}
                  aria-label={t('clinicalChat.call.sendAudio')}
                  aria-describedby={showSendAudioHint ? sendAudioHintId : undefined}
                  title={t('clinicalChat.call.sendAudio')}
                >
                  {isSubmittingUtterance ? (
                    <LoaderCircle className="h-5 w-5 motion-safe:animate-spin" aria-hidden="true" />
                  ) : (
                    <SendHorizontal className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </div>
            </article>
          </div>
        </div>
        {showSendAudioHint && <p id={sendAudioHintId} hidden={!showStudentWave} className="call-send-coachmark dialog-annotation text-left">
          {t('clinicalChat.call.sendAudioHint')}
        </p>}
        </div>
        <div hidden={!waitingForPatient} aria-hidden={!waitingForPatient || undefined}>
          <div className="min-h-0 overflow-hidden">
            <div role={waitingForPatient ? 'status' : undefined} className="flex items-start gap-layout px-inset py-layout text-left text-neutral-500 secondary-text leading-4">
              <span className="mt-1 h-2 w-2 shrink-0 motion-safe:animate-pulse rounded-full bg-brand-500" />
              {t('clinicalChat.call.patientThinking')}
            </div>
          </div>
        </div>
        {audioError && <div className="text-center text-warning-700 secondary-text" role="alert">
          <p>{audioError}</p>
          {failedPatientMessage && <button type="button" className="ui-button ui-button--secondary"
            onClick={() => {
              if (blockedPlaybackRef.current) blockedPlaybackRef.current();
              else void playMessage(failedPatientMessage);
            }}>{t(blockedPlaybackRef.current ? 'clinicalChat.call.playPatientAudio' : 'common.retry')}</button>}
          {failedPatientMessage && (
            <button type="button" className="ui-button ui-button--secondary"
              onClick={() => {
                setAudioError(null);
                setFailedPatientMessage(null);
                stopAudio(failedPatientMessage.id, true);
              }}>{t('clinicalChat.call.continueWithoutPatientAudio')}</button>
          )}
        </div>}
        </div>
      </div>
    </section>
  );
};
