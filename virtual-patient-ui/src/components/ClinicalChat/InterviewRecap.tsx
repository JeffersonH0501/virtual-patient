import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getInterviewRecap, resolveRecordingSource} from '../../services/recordings';
import {InterviewRecap as InterviewRecapData, RecapTurn} from '../../types/recording';
import {Message} from '../../types/message';
import {Info, Pause, Play, Speaker, X} from '../../icons';
import {Modal} from '../common/Modal';

type Props = {
  interviewId: number;
  messages?: Message[];
};

const formatElapsed = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, '0')}`;
};

const legacyTurns = (messages: Message[] = []): RecapTurn[] => messages.map((message) => ({
  turnId: `legacy-${message.id}`,
  messageId: message.id,
  speaker: message.senderType === 'user' ? 'student' : 'patient',
  transcript: message.content,
  inputSource: 'legacy_message',
  timingSource: 'unavailable',
  timingQuality: 'unavailable',
}));

export const InterviewRecap = ({interviewId, messages}: Props) => {
  const {t} = useTranslation();
  const [recap, setRecap] = useState<InterviewRecapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(1);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const [detailTurn, setDetailTurn] = useState<RecapTurn | null>(null);
  const studentVideoRef = useRef<HTMLVideoElement>(null);
  const patientVideoRef = useRef<HTMLVideoElement>(null);
  const studentAudioRef = useRef<HTMLAudioElement>(null);
  const patientAudioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioElementsConnectedRef = useRef(false);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    let retryTimer: number | null = null;
    setLoading(true);
    const loadRecap = async () => {
      try {
        const nextRecap = await getInterviewRecap(interviewId);
        if (!active) return;
        setRecap(nextRecap);
        const processingStatus = nextRecap.observationProcessing?.status;
        if (processingStatus === 'queued' || processingStatus === 'processing') {
          retryTimer = window.setTimeout(loadRecap, 3000);
        }
      } catch {
        if (active) {
          setRecap({
            interviewId,
            recordingStatus: 'unavailable',
            turns: legacyTurns(messages),
          });
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void loadRecap();
    return () => {
      active = false;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [interviewId, messages]);

  useEffect(() => {
    if (!detailTurn || !recap?.turns) return;
    const updatedTurn = recap.turns.find((turn) => turn.turnId === detailTurn.turnId);
    if (updatedTurn) setDetailTurn(updatedTurn);
  }, [detailTurn, recap?.turns]);

  const sources = useMemo(() => ({
    studentVideo: resolveRecordingSource(recap?.studentVideoSource),
    patientVideo: resolveRecordingSource(recap?.patientVideoSource),
    studentAudio: resolveRecordingSource(recap?.studentAudioSource),
    patientAudio: resolveRecordingSource(recap?.patientAudioSource),
  }), [recap]);
  const hasMedia = Object.values(sources).some(Boolean);
  const turns = recap?.turns?.length ? recap.turns : legacyTurns(messages);

  const mediaElements = useCallback((): HTMLMediaElement[] => [
    studentVideoRef.current,
    patientVideoRef.current,
    studentAudioRef.current,
    patientAudioRef.current,
  ].filter((element): element is HTMLMediaElement => Boolean(element?.src)), []);

  const masterElement = useCallback((): HTMLMediaElement | null =>
    studentVideoRef.current?.src
      ? studentVideoRef.current
      : patientVideoRef.current?.src
        ? patientVideoRef.current
        : studentAudioRef.current?.src
          ? studentAudioRef.current
          : patientAudioRef.current,
  []);

  const ensureAudioGraph = useCallback(async () => {
    if (audioElementsConnectedRef.current) {
      await audioContextRef.current?.resume();
      return;
    }
    const AudioContextConstructor = window.AudioContext;
    if (!AudioContextConstructor) return;
    const context = new AudioContextConstructor();
    [studentAudioRef.current, patientAudioRef.current].forEach((element) => {
      if (!element?.src) return;
      const source = context.createMediaElementSource(element);
      const gain = context.createGain();
      gain.gain.value = 1;
      source.connect(gain).connect(context.destination);
    });
    audioContextRef.current = context;
    audioElementsConnectedRef.current = true;
    await context.resume();
  }, []);

  const stopClock = useCallback(() => {
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
  }, []);

  const runClock = useCallback(() => {
    const master = masterElement();
    if (!master) return;
    const nextTime = master.currentTime;
    setCurrentTime(nextTime);
    mediaElements().forEach((element) => {
      if (element !== master && Math.abs(element.currentTime - nextTime) > 0.15) {
        element.currentTime = nextTime;
      }
    });
    if (!master.paused && !master.ended) animationFrameRef.current = requestAnimationFrame(runClock);
  }, [masterElement, mediaElements]);

  const play = useCallback(async () => {
    if (!hasMedia) return;
    if (duration > 0 && currentTime >= duration) {
      mediaElements().forEach((element) => {
        element.currentTime = 0;
      });
      setCurrentTime(0);
    }
    await ensureAudioGraph();
    const elements = mediaElements();
    const results = await Promise.allSettled(elements.map((element) => element.play()));
    if (!results.some((result) => result.status === 'fulfilled')) return;
    setPlaying(true);
    stopClock();
    animationFrameRef.current = requestAnimationFrame(runClock);
  }, [currentTime, duration, ensureAudioGraph, hasMedia, mediaElements, runClock, stopClock]);

  const pause = useCallback(() => {
    mediaElements().forEach((element) => element.pause());
    setPlaying(false);
    stopClock();
  }, [mediaElements, stopClock]);

  const changeVolume = (nextVolume: number) => {
    mediaElements().forEach((element) => {
      element.volume = nextVolume;
    });
    setVolume(nextVolume);
  };

  const seek = useCallback((seconds: number) => {
    const nextTime = Math.max(0, Math.min(seconds, duration || seconds));
    mediaElements().forEach((element) => {
      element.currentTime = nextTime;
    });
    setCurrentTime(nextTime);
  }, [duration, mediaElements]);

  useEffect(() => () => {
    stopClock();
    mediaElements().forEach((element) => element.pause());
    void audioContextRef.current?.close();
  }, [mediaElements, stopClock]);

  const timedTurns = turns.filter((turn) => typeof turn.startMs === 'number');
  const visibleTurns = hasMedia && timedTurns.length > 0
    ? turns.filter(
      (turn) => typeof turn.startMs !== 'number' || turn.startMs <= currentTime * 1000,
    )
    : turns;
  const activeTurnIds = new Set(
    timedTurns
      .filter(
        (turn) => (turn.startMs ?? Number.MAX_SAFE_INTEGER) <= currentTime * 1000
          && (turn.endMs ?? -1) >= currentTime * 1000,
      )
      .map((turn) => turn.turnId),
  );

  const selectTurn = (turn: RecapTurn) => {
    setSelectedTurnId(turn.turnId);
    if (hasMedia && typeof turn.startMs === 'number') seek(turn.startMs / 1000);
  };

  const updateDuration = () => {
    const mediaDuration = Math.max(
      recap?.durationMs ? recap.durationMs / 1000 : 0,
      ...mediaElements().map((element) => Number.isFinite(element.duration) ? element.duration : 0),
    );
    setDuration(mediaDuration);
  };

  const handleEnded = () => {
    setPlaying(false);
    stopClock();
    setCurrentTime(duration);
  };

  const visibleParaverbal = detailTurn?.paraverbal?.interpretability
    ?.acousticTemporal?.labels;

  return (
    <section className="flex min-h-0 flex-1 flex-col" aria-label={t('clinicalChat.recap.title')}>
      <header className="flex min-h-12 shrink-0 items-center border-b border-slate-200 bg-white px-4 text-left sm:px-5">
        <h2 className="component-title">{t('clinicalChat.recap.title')}</h2>
      </header>
      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-hidden p-3 sm:p-4">
        {loading ? (
          <div className="flex h-40 items-center justify-center text-sm text-slate-500">{t('common.loading')}</div>
        ) : (
          <div className="mx-auto flex h-full min-h-0 w-full max-w-5xl flex-col gap-4">
            {hasMedia ? (
              <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-950">
                <div className="grid grid-cols-1 gap-px bg-slate-700 sm:grid-cols-2">
                  <div className="relative aspect-video bg-slate-900">
                    {sources.patientVideo ? (
                      <video
                        ref={patientVideoRef}
                        src={sources.patientVideo}
                        crossOrigin="use-credentials"
                        muted
                        playsInline
                        preload="metadata"
                        onLoadedMetadata={updateDuration}
                        onEnded={handleEnded}
                        className="h-full w-full object-contain"
                      />
                    ) : <div className="flex h-full items-center justify-center text-xs text-slate-400">{t('clinicalChat.recap.patientVideoUnavailable')}</div>}
                    <span className="absolute bottom-2 left-2 rounded bg-black/60 px-2 py-1 text-xs text-white">{t('clinicalChat.call.patient')}</span>
                  </div>
                  <div className="relative aspect-video bg-slate-900">
                    {sources.studentVideo ? (
                      <video
                        ref={studentVideoRef}
                        src={sources.studentVideo}
                        crossOrigin="use-credentials"
                        muted
                        playsInline
                        preload="metadata"
                        onLoadedMetadata={updateDuration}
                        onEnded={handleEnded}
                        className="h-full w-full object-contain"
                      />
                    ) : <div className="flex h-full items-center justify-center text-xs text-slate-400">{t('clinicalChat.recap.studentVideoUnavailable')}</div>}
                    <span className="absolute bottom-2 left-2 rounded bg-black/60 px-2 py-1 text-xs text-white">{t('clinicalChat.call.student')}</span>
                  </div>
                </div>
                <audio ref={studentAudioRef} src={sources.studentAudio ?? undefined} crossOrigin="use-credentials" preload="metadata" onLoadedMetadata={updateDuration} />
                <audio ref={patientAudioRef} src={sources.patientAudio ?? undefined} crossOrigin="use-credentials" preload="metadata" onLoadedMetadata={updateDuration} />
                <div className="flex items-center gap-2.5 bg-slate-900 px-3 py-2 text-white">
                  <button
                    type="button"
                    onClick={playing ? pause : () => void play()}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white hover:bg-blue-500 [&_svg]:h-4 [&_svg]:w-4"
                    aria-label={playing ? t('clinicalChat.recap.pause') : t('clinicalChat.recap.play')}
                  >
                    {playing ? <Pause color="currentColor" /> : <Play color="currentColor" />}
                  </button>
                  <span className="w-10 text-right text-xs tabular-nums">{formatElapsed(currentTime)}</span>
                  <input
                    type="range"
                    min={0}
                    max={Math.max(duration, 0.01)}
                    step={0.05}
                    value={Math.min(currentTime, duration || currentTime)}
                    onChange={(event) => seek(Number(event.target.value))}
                    className="min-w-0 flex-1 accent-blue-500"
                    aria-label={t('clinicalChat.recap.timeline')}
                  />
                  <span className="w-10 text-xs tabular-nums">{formatElapsed(duration)}</span>
                  <label className="group flex shrink-0 items-center justify-end gap-1.5" title={t('clinicalChat.recap.volume')}>
                    <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><Speaker color="currentColor" /></span>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={volume}
                      onChange={(event) => changeVolume(Number(event.target.value))}
                      className="w-0 min-w-0 cursor-pointer overflow-hidden opacity-0 accent-blue-500 transition-recap duration-150 group-hover:w-16 group-hover:opacity-100 group-focus-within:w-16 group-focus-within:opacity-100 sm:group-hover:w-20 sm:group-focus-within:w-20"
                      aria-label={t('clinicalChat.recap.volume')}
                    />
                  </label>
                </div>
              </div>
            ) : (
              <div className="flex min-h-40 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 text-center text-sm text-slate-500">
                {t('clinicalChat.recap.unavailable')}
              </div>
            )}

            <div
              className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto pr-1 scrollbar-hidden"
              aria-live="polite"
            >
              <div className="flex flex-col gap-3 pb-1">
              {visibleTurns.map((turn) => {
                const isStudent = turn.speaker === 'student';
                const active = activeTurnIds.has(turn.turnId) || selectedTurnId === turn.turnId;
                return (
                  <div
                    key={turn.turnId}
                    className={`flex items-start gap-2 ${
                      isStudent ? 'ml-1 sm:ml-8' : 'mr-1 flex-row-reverse sm:mr-8'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setDetailTurn(turn)}
                      className="mt-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-blue-700 [&_svg]:h-4 [&_svg]:w-4"
                      aria-label={t('clinicalChat.recap.turnInfo')}
                      title={t('clinicalChat.recap.turnInfo')}
                    >
                      <Info color="currentColor" />
                    </button>
                    <button
                      type="button"
                      onClick={() => selectTurn(turn)}
                      className={`min-w-0 flex-1 rounded-xl border px-3 py-2.5 text-left transition-colors ${
                        isStudent
                          ? 'border-blue-100 bg-blue-50'
                          : 'border-slate-200 bg-slate-100'
                      } ${active ? 'ring-2 ring-inset ring-blue-400' : ''}`}
                    >
                      <p className="whitespace-pre-wrap text-sm leading-5 text-slate-800">{turn.transcript}</p>
                      {typeof turn.startMs === 'number' && (
                        <span className="mt-1 block text-right text-timestamp text-slate-400">{formatElapsed(turn.startMs / 1000)}</span>
                      )}
                    </button>
                  </div>
                );
              })}
              </div>
            </div>
          </div>
        )}
      </div>
      <Modal
        open={Boolean(detailTurn)}
        closeAction={() => setDetailTurn(null)}
        size="large"
      >
        {detailTurn && (
          <div className="flex max-h-dialog min-h-0 flex-col overflow-hidden">
            <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h3 className="text-base font-semibold text-slate-800">{t('clinicalChat.recap.turnDetails')}</h3>
              <button
                type="button"
                onClick={() => setDetailTurn(null)}
                className="dialog-close-button"
                aria-label={t('common.close')}
                title={t('common.close')}
              >
                <X color="currentColor" />
              </button>
            </header>
            <div className="grid min-h-0 grid-cols-1 gap-3 overflow-y-auto px-5 py-4 text-sm text-slate-700 scrollbar-hidden md:grid-cols-2 xl:grid-cols-4">
              <section className="min-w-0 rounded-lg border border-slate-200 p-3">
                <h4 className="mb-3 font-semibold text-slate-800">{t('clinicalChat.recap.generalInformation')}</h4>
                <pre className="whitespace-pre-wrap break-words rounded bg-slate-50 p-3 text-xs text-slate-700">
                  {JSON.stringify({
                    turnId: detailTurn.turnId,
                    messageId: detailTurn.messageId ?? null,
                    speaker: detailTurn.speaker,
                    transcript: detailTurn.transcript,
                    startMs: detailTurn.startMs ?? null,
                    endMs: detailTurn.endMs ?? null,
                    inputSource: detailTurn.inputSource,
                    timingSource: detailTurn.timingSource,
                    timingQuality: detailTurn.timingQuality,
                  }, null, 2)}
                </pre>
              </section>
              {([
                [
                  'clinicalChat.recap.paraverbal',
                  visibleParaverbal ? {labels: visibleParaverbal} : null,
                ],
                ['clinicalChat.recap.nonverbal', detailTurn.nonverbalFeatures],
                ['clinicalChat.recap.pyfeatBenchmark', detailTurn.pyfeatNonverbalFeatures],
              ] as const).map(([title, observation]) => (
                <section key={title} className="min-w-0 rounded-lg border border-slate-200 p-3">
                  <h4 className="mb-3 font-semibold text-slate-800">{t(title)}</h4>
                  {observation ? (
                    <pre className="whitespace-pre-wrap break-words rounded bg-slate-50 p-3 text-xs text-slate-700">
                      {JSON.stringify(observation, null, 2)}
                    </pre>
                  ) : <p>{
                    recap?.observationProcessing?.status === 'queued'
                    || recap?.observationProcessing?.status === 'processing'
                      ? t('clinicalChat.recap.processingObservations')
                      : t('clinicalChat.recap.notAvailable')
                  }</p>}
                </section>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
};
