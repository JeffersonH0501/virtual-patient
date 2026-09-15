import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getInterviewRecap, resolveRecordingSource} from '../../services/recordings';
import {FamilyLabel, InterviewRecap as InterviewRecapData, RecapTurn} from '../../types/recording';
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

const formatTimestamp = (milliseconds?: number | null): string | null => {
  if (typeof milliseconds !== 'number') return null;
  const seconds = milliseconds / 1000;
  const minutes = Math.floor(seconds / 60);
  const remainder = (seconds % 60).toFixed(3).padStart(6, '0');
  return `${minutes}:${remainder} (${milliseconds} ms)`;
};

const formatMetricValue = (value?: number | null): string | null => {
  if (typeof value !== 'number') return null;
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
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

  const currentMs = currentTime * 1000;
  const timedTurns = turns.filter((turn) => typeof turn.startMs === 'number');
  const visibleTurns = hasMedia && timedTurns.length > 0
    ? turns.filter(
      (turn) => typeof turn.startMs !== 'number' || (turn.startMs ?? 0) <= currentMs,
    )
    : turns;
  // A single active turn: the most recent one that has already started at the
  // current playback time. Relying only on startMs (not the [start, end]
  // interval) guarantees at most one highlighted bubble even if timing windows
  // overlap.
  const startedTurns = timedTurns.filter((turn) => (turn.startMs ?? 0) <= currentMs);
  const activeTurnId = hasMedia && startedTurns.length > 0
    ? startedTurns.reduce((latest, turn) => ((turn.startMs ?? 0) >= (latest.startMs ?? 0) ? turn : latest)).turnId
    : null;

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

  const observationUnavailable = t('clinicalChat.recap.notAvailable');

  const renderMetricRow = (labelKey: string, value?: number | null, unitKey?: string) => (
    <div className="turn-detail-row" key={labelKey}>
      <dt>{t(labelKey)}</dt>
      <dd>{formatMetricValue(value) ?? observationUnavailable}</dd>
      <span>{unitKey && typeof value === 'number' ? t(unitKey) : ''}</span>
    </div>
  );

  // Renders the single integrated label for a family. When the label is present
  // and "ok", the localized value is shown. Otherwise the family is surfaced as
  // unavailable with the backend reason/status when known; no label is ever
  // fabricated for a family the backend did not compute (e.g. legacy payloads
  // report every family except paraverbal `temporal` as unavailable).
  const renderFamilyLabel = (label?: FamilyLabel) => {
    const isOk = label?.status === 'ok' && Boolean(label?.value);
    const detail = label?.reason ?? label?.status;
    return (
      <div className="turn-detail-row turn-detail-row--label">
        <dt>{t('clinicalChat.recap.integratedLabel')}</dt>
        <dd>
          {isOk
            ? label!.value
            : detail
              ? t('clinicalChat.recap.labelUnavailableWithReason', {
                reason: t(`clinicalChat.recap.observationStatus.${detail}`, {
                  defaultValue: detail,
                }),
              })
              : t('clinicalChat.recap.observationStatus.unavailable')}
        </dd>
        <span />
      </div>
    );
  };

  const paraverbal = detailTurn?.paraverbal?.processed;
  const paraverbalLabels = detailTurn?.paraverbal?.integratedLabels;
  const nonverbal = detailTurn?.nonverbalFeatures?.processed;
  const nonverbalLabels = detailTurn?.nonverbalFeatures?.integratedLabels;

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
                const active = turn.turnId === activeTurnId;
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
                      className="mt-1.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-blue-700 [&_svg]:h-4 [&_svg]:w-4"
                      aria-label={t('clinicalChat.recap.turnInfo')}
                      title={t('clinicalChat.recap.turnInfo')}
                    >
                      <Info color="currentColor" />
                    </button>
                    <div
                      className={`min-w-0 flex-1 rounded-xl border p-3 text-left transition-colors ${
                        isStudent
                          ? 'border-blue-100 bg-blue-50'
                          : 'border-slate-200 bg-slate-100'
                      } ${active ? 'ring-2 ring-inset ring-blue-400' : ''}`}
                    >
                      <p className="whitespace-pre-wrap text-sm leading-5 text-slate-800">{turn.transcript}</p>
                      {typeof turn.startMs === 'number' && (
                        <span className="block text-right text-timestamp leading-none text-slate-400">{formatElapsed(turn.startMs / 1000)}</span>
                      )}
                    </div>
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
        size="extralarge"
      >
        {detailTurn && (
          <div className="dialog-shell">
            <header className="dialog-header">
              <h3 className="dialog-title">{t('clinicalChat.recap.turnDetails')}</h3>
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
            <div className="dialog-content turn-detail-content scrollbar-hidden">
              <section className="turn-detail-column">
                <h4>{t('clinicalChat.recap.generalInformation')}</h4>
                <dl className="turn-detail-general">
                  <div className="turn-detail-general-item">
                    <dt>{t('clinicalChat.recap.speaker')}</dt>
                    <dd>{t(`clinicalChat.recap.speakers.${detailTurn.speaker}`)}</dd>
                  </div>
                  <div className="turn-detail-general-item">
                    <dt>{t('clinicalChat.recap.start')}</dt>
                    <dd>{formatTimestamp(detailTurn.startMs) ?? t('clinicalChat.recap.notAvailable')}</dd>
                  </div>
                  <div className="turn-detail-general-item">
                    <dt>{t('clinicalChat.recap.end')}</dt>
                    <dd>{formatTimestamp(detailTurn.endMs) ?? t('clinicalChat.recap.notAvailable')}</dd>
                  </div>
                  <div className="turn-detail-general-item">
                    <dt>{t('clinicalChat.recap.transcript')}</dt>
                    <dd>{detailTurn.transcript || t('clinicalChat.recap.notAvailable')}</dd>
                  </div>
                </dl>
              </section>

              <section className="turn-detail-column">
                <h4>{t('clinicalChat.recap.paraverbal')}</h4>
                {detailTurn.paraverbal ? (
                  <div className="turn-detail-groups">
                    <div className="turn-detail-group">
                      <h5>{t('clinicalChat.recap.families.temporal')}</h5>
                      <dl>
                        {renderFamilyLabel(paraverbalLabels?.temporal)}
                        {renderMetricRow('clinicalChat.recap.metrics.speechRateWpm', paraverbal?.speechRateWpm, 'clinicalChat.recap.units.wordsPerMinute')}
                        {renderMetricRow('clinicalChat.recap.metrics.articulationRateWpm', paraverbal?.articulationRateWpm, 'clinicalChat.recap.units.wordsPerMinute')}
                        {renderMetricRow('clinicalChat.recap.metrics.pauseCount', paraverbal?.pauseCount, 'clinicalChat.recap.units.count')}
                        {renderMetricRow('clinicalChat.recap.metrics.totalPauseDurationMs', paraverbal?.totalPauseDurationMs, 'clinicalChat.recap.units.milliseconds')}
                        {renderMetricRow('clinicalChat.recap.metrics.medianPauseDurationMs', paraverbal?.medianPauseDurationMs, 'clinicalChat.recap.units.milliseconds')}
                        {renderMetricRow('clinicalChat.recap.metrics.pauseTimeRatio', paraverbal?.pauseTimeRatio, 'clinicalChat.recap.units.ratio')}
                      </dl>
                    </div>
                    <div className="turn-detail-group">
                      <h5>{t('clinicalChat.recap.families.prosodicLevel')}</h5>
                      <dl>
                        {renderFamilyLabel(paraverbalLabels?.prosodicLevel)}
                        {renderMetricRow('clinicalChat.recap.metrics.f0MedianSemitones', paraverbal?.f0MedianSemitones, 'clinicalChat.recap.units.semitones')}
                        {renderMetricRow('clinicalChat.recap.metrics.medianLoudness', paraverbal?.medianLoudness, 'clinicalChat.recap.units.loudness')}
                      </dl>
                    </div>
                    <div className="turn-detail-group">
                      <h5>{t('clinicalChat.recap.families.prosodicModulation')}</h5>
                      <dl>
                        {renderFamilyLabel(paraverbalLabels?.prosodicModulation)}
                        {renderMetricRow('clinicalChat.recap.metrics.f0P20P80RangeSemitones', paraverbal?.f0P20P80RangeSemitones, 'clinicalChat.recap.units.semitones')}
                        {renderMetricRow('clinicalChat.recap.metrics.loudnessP20P80Range', paraverbal?.loudnessP20P80Range, 'clinicalChat.recap.units.loudness')}
                      </dl>
                    </div>
                  </div>
                ) : (
                  <p className="turn-detail-empty">{t('clinicalChat.recap.paraverbalUnavailable')}</p>
                )}
              </section>

              <section className="turn-detail-column">
                <h4>{t('clinicalChat.recap.nonverbal')}</h4>
                {detailTurn.nonverbalFeatures ? (
                  <div className="turn-detail-groups">
                    <div className="turn-detail-group">
                      <h5>{t('clinicalChat.recap.families.visualOrientation')}</h5>
                      <dl>
                        {renderFamilyLabel(nonverbalLabels?.visualOrientation)}
                        {renderMetricRow('clinicalChat.recap.metrics.visualAlignmentRatio', nonverbal?.visualAlignmentRatio, 'clinicalChat.recap.units.ratio')}
                        {renderMetricRow('clinicalChat.recap.metrics.medianVisualAlignmentDwellMs', nonverbal?.medianVisualAlignmentDwellMs, 'clinicalChat.recap.units.milliseconds')}
                      </dl>
                    </div>
                    <div className="turn-detail-group">
                      <h5>{t('clinicalChat.recap.families.headGesturalFeedback')}</h5>
                      <dl>
                        {renderFamilyLabel(nonverbalLabels?.headGesturalFeedback)}
                        {renderMetricRow('clinicalChat.recap.metrics.nodCount', nonverbal?.nodCount, 'clinicalChat.recap.units.count')}
                        {renderMetricRow('clinicalChat.recap.metrics.nodRateMin', nonverbal?.nodRateMin, 'clinicalChat.recap.units.eventsPerMinute')}
                      </dl>
                    </div>
                    <div className="turn-detail-group">
                      <h5>{t('clinicalChat.recap.families.facialExpressivity')}</h5>
                      <dl>
                        {renderFamilyLabel(nonverbalLabels?.facialExpressivity)}
                        {renderMetricRow('clinicalChat.recap.metrics.smileActivityRatio', nonverbal?.smileActivityRatio, 'clinicalChat.recap.units.ratio')}
                        {renderMetricRow('clinicalChat.recap.metrics.meanSmileActivation', nonverbal?.meanSmileActivation, 'clinicalChat.recap.units.auActivation')}
                      </dl>
                    </div>
                  </div>
                ) : (
                  <p className="turn-detail-empty">{t('clinicalChat.recap.nonverbalUnavailable')}</p>
                )}
              </section>
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
};

