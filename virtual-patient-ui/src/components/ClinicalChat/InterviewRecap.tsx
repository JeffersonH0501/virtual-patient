import {ReactNode, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getInterviewRecap, resolveRecordingSource} from '../../services/recordings';
import {FamilyLabel, InterviewRecap as InterviewRecapData, RecapTurn} from '../../types/recording';
import {Message} from '../../types/message';
import {Info, Pause, Play, Speaker, X} from '../../icons';
import {Modal} from '../common/Modal';

type Props = {
  interviewId: number;
  messages?: Message[];
  /**
   * Disables the per-turn info buttons and prevents opening the detail dialog
   * while the multimodal analysis is being regenerated, so the student cannot
   * inspect stale per-turn evidence until the fresh results are ready.
   */
  infoDisabled?: boolean;
};

// Small offset added when seeking to a turn's start so the playback time lands
// firmly inside the turn window and the playback-driven highlight marks it.
const TURN_SEEK_OFFSET_MS = 50;

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

// Total elapsed time of a turn (end - start), rendered like a timestamp with an
// exact millisecond value. Returns null unless both bounds are numeric and the
// span is non-negative, so a fabricated or malformed window is shown as "not
// available" rather than a misleading duration.
const formatDuration = (startMs?: number | null, endMs?: number | null): string | null => {
  if (typeof startMs !== 'number' || typeof endMs !== 'number') return null;
  const durationMs = endMs - startMs;
  if (durationMs < 0) return null;
  return formatTimestamp(durationMs);
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

export const InterviewRecap = ({interviewId, messages, infoDisabled = false}: Props) => {
  const {t} = useTranslation();
  const [recap, setRecap] = useState<InterviewRecapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(1);
  const [detailTurn, setDetailTurn] = useState<RecapTurn | null>(null);
  // The turn whose bubble shows the blue outline. It is set directly (and
  // immediately) when a bubble is clicked, and also kept in sync with playback
  // by the master element's time events. Making it explicit state — rather than
  // deriving it from a possibly-stale currentTime during render — is what makes
  // the click reliably highlight the clicked turn.
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const studentVideoRef = useRef<HTMLVideoElement>(null);
  const patientVideoRef = useRef<HTMLVideoElement>(null);
  const studentAudioRef = useRef<HTMLAudioElement>(null);
  const patientAudioRef = useRef<HTMLAudioElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioElementsConnectedRef = useRef(false);
  // Latest turns, kept in a ref so the time-event callbacks can compute the
  // active turn without being re-created on every render.
  const turnsRef = useRef<RecapTurn[]>([]);

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

  // Silently refresh the per-turn evidence once a regeneration finishes. This
  // never toggles the panel's full-screen loading state, so the recap keeps its
  // usual appearance; only the info buttons are inactive while `infoDisabled` is
  // true. It skips the initial mount (infoDisabled starts false).
  const wasInfoDisabledRef = useRef(false);
  useEffect(() => {
    const justFinished = wasInfoDisabledRef.current && !infoDisabled;
    wasInfoDisabledRef.current = infoDisabled;
    if (!justFinished) return;
    let active = true;
    void (async () => {
      try {
        const nextRecap = await getInterviewRecap(interviewId);
        if (active) setRecap(nextRecap);
      } catch {
        // Keep the existing recap on a transient refresh failure.
      }
    })();
    return () => {
      active = false;
    };
  }, [infoDisabled, interviewId]);

  useEffect(() => {
    if (!detailTurn || !recap?.turns) return;
    const updatedTurn = recap.turns.find((turn) => turn.turnId === detailTurn.turnId);
    if (updatedTurn) setDetailTurn(updatedTurn);
  }, [detailTurn, recap?.turns]);

  // Close the per-turn detail dialog if a regeneration starts while it is open:
  // the shown evidence is about to be replaced, so it must not stay inspectable.
  useEffect(() => {
    if (infoDisabled) setDetailTurn(null);
  }, [infoDisabled]);

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

  // The active turn for a given time (ms): the turn whose start is the largest
  // one at or before that time, breaking ties by conversational sequence.
  // During the inter-turn dead time the next turn has not started yet, so this
  // keeps the just-ended turn active. Falls back to the first turn so there is
  // always exactly one highlight.
  const turnIdAtTime = useCallback((ms: number): string | null => {
    const currentTurns = turnsRef.current;
    let best: string | null = currentTurns[0]?.turnId ?? null;
    let bestStartMs = -1;
    currentTurns.forEach((turn) => {
      if (typeof turn.startMs !== 'number') return;
      if (turn.startMs <= ms && turn.startMs >= bestStartMs) {
        bestStartMs = turn.startMs;
        best = turn.turnId;
      }
    });
    return best;
  }, []);

  // Keep the displayed time, the other media elements, and the active-turn
  // highlight aligned to the master's clock. Called on the master's native
  // `timeupdate`/`seeked` events, which always report the element's real
  // position (even right after a seek), so there is no stale read and no manual
  // animation-frame loop to get out of sync.
  const syncFromMaster = useCallback(() => {
    const master = masterElement();
    if (!master) return;
    const nextTime = master.currentTime;
    setCurrentTime(nextTime);
    setActiveTurnId(turnIdAtTime(nextTime * 1000));
    mediaElements().forEach((element) => {
      if (element !== master && Math.abs(element.currentTime - nextTime) > 0.15) {
        element.currentTime = nextTime;
      }
    });
  }, [masterElement, mediaElements, turnIdAtTime]);

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
  }, [currentTime, duration, ensureAudioGraph, hasMedia, mediaElements]);

  const pause = useCallback(() => {
    mediaElements().forEach((element) => element.pause());
    setPlaying(false);
  }, [mediaElements]);

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
    // Update the highlight from the requested time directly, so it is correct
    // immediately regardless of when the media applies the seek.
    setActiveTurnId(turnIdAtTime(nextTime * 1000));
  }, [duration, mediaElements, turnIdAtTime]);

  // Jump the synchronized playback to the start of a turn when its transcript
  // bubble is clicked, and highlight that turn immediately. The highlight is set
  // from the clicked turn itself (not derived from a not-yet-applied seek), so
  // it never disappears while the media element catches up. Only turns with a
  // measured start over available media can be targeted.
  const seekToTurn = useCallback((turn: RecapTurn) => {
    if (!hasMedia || typeof turn.startMs !== 'number') return;
    setActiveTurnId(turn.turnId);
    seek((turn.startMs + TURN_SEEK_OFFSET_MS) / 1000);
  }, [hasMedia, seek]);

  useEffect(() => () => {
    mediaElements().forEach((element) => element.pause());
    void audioContextRef.current?.close();
  }, [mediaElements]);

  // Drive currentTime from the master element's native events. `timeupdate`
  // fires during playback and `seeked` fires after any seek (bubble click or
  // timeline drag), both always reporting the element's real position, so the
  // active-turn highlight can never lag behind or get stuck.
  useEffect(() => {
    const master = masterElement();
    if (!master) return undefined;
    master.addEventListener('timeupdate', syncFromMaster);
    master.addEventListener('seeked', syncFromMaster);
    return () => {
      master.removeEventListener('timeupdate', syncFromMaster);
      master.removeEventListener('seeked', syncFromMaster);
    };
  }, [masterElement, syncFromMaster, hasMedia, recap]);

  // Keep the turns ref current, and initialize/repair the highlight only when it
  // is missing or points at a turn that no longer exists (e.g. before the first
  // event or after a recap refresh). Playback and seeks own the highlight
  // otherwise, so this must not overwrite a valid selection.
  useEffect(() => {
    turnsRef.current = turns;
    setActiveTurnId((previous) => {
      if (previous && turns.some((turn) => turn.turnId === previous)) return previous;
      return turnIdAtTime(currentTime * 1000);
    });
  }, [turns, currentTime, turnIdAtTime]);

  // Every turn is always shown; bubbles no longer appear/disappear with the
  // playback position.
  const visibleTurns = turns;

  const updateDuration = () => {
    const mediaDuration = Math.max(
      recap?.durationMs ? recap.durationMs / 1000 : 0,
      ...mediaElements().map((element) => Number.isFinite(element.duration) ? element.duration : 0),
    );
    setDuration(mediaDuration);
  };

  const handleEnded = () => {
    setPlaying(false);
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

  // Localize a base/integrated label VALUE (e.g. `sustained_visual_orientation`)
  // through the `labelValues` i18n dictionary, falling back to the raw value so
  // an unmapped label is still shown rather than blank.
  const localizeLabelValue = (value: string) =>
    t(`clinicalChat.recap.labelValues.${value}`, {defaultValue: value});

  // Resolve one FamilyLabel to its display text: the localized value when "ok",
  // otherwise a plain "No disponible" (the raw reason code is intentionally not
  // surfaced to the reader). No label is ever fabricated for a family/feature
  // the backend did not compute.
  const labelDisplay = (label?: FamilyLabel): string => {
    const isOk = label?.status === 'ok' && Boolean(label?.value);
    if (isOk) return localizeLabelValue(label!.value as string);
    return observationUnavailable;
  };

  // Ordered level scales for the individual (base) labels. Instead of repeating
  // the row label inside the value, each base label shows its full scale (e.g.
  // baja · típica · alta) and highlights the observed level in bold. Each entry
  // maps a backend value CODE suffix to a short `levels` i18n key.
  const levelScales: Record<string, {code: string; levelKey: string}[]> = {
    speechRateWpm: [{code: 'speech_rate_low', levelKey: 'low'}, {code: 'speech_rate_typical', levelKey: 'typical'}, {code: 'speech_rate_high', levelKey: 'high'}],
    articulationRateWpm: [{code: 'articulation_rate_low', levelKey: 'low'}, {code: 'articulation_rate_typical', levelKey: 'typical'}, {code: 'articulation_rate_high', levelKey: 'high'}],
    medianPauseDurationMs: [{code: 'pause_duration_brief', levelKey: 'brief'}, {code: 'pause_duration_typical', levelKey: 'typical'}, {code: 'pause_duration_long', levelKey: 'long'}],
    pauseFrequencyPerMin: [{code: 'pause_frequency_low', levelKey: 'low'}, {code: 'pause_frequency_typical', levelKey: 'typical'}, {code: 'pause_frequency_high', levelKey: 'high'}],
    pauseTimeRatio: [{code: 'pause_load_low', levelKey: 'low'}, {code: 'pause_load_typical', levelKey: 'typical'}, {code: 'pause_load_high', levelKey: 'high'}],
    relativePitchShiftSt: [{code: 'relative_pitch_low', levelKey: 'lowM'}, {code: 'relative_pitch_typical', levelKey: 'typicalM'}, {code: 'relative_pitch_high', levelKey: 'highM'}],
    medianLoudness: [{code: 'loudness_low', levelKey: 'low'}, {code: 'loudness_typical', levelKey: 'typical'}, {code: 'loudness_high', levelKey: 'high'}],
    f0P20P80RangeSemitones: [{code: 'intonation_monotone', levelKey: 'monotone'}, {code: 'intonation_typical', levelKey: 'typical'}, {code: 'intonation_variable', levelKey: 'variable'}],
    loudnessP20P80Range: [{code: 'loudness_variability_low', levelKey: 'low'}, {code: 'loudness_variability_typical', levelKey: 'typical'}, {code: 'loudness_variability_high', levelKey: 'high'}],
    visualAlignmentRatio: [{code: 'visual_alignment_low', levelKey: 'low'}, {code: 'visual_alignment_mid', levelKey: 'mid'}, {code: 'visual_alignment_high', levelKey: 'high'}],
    medianVisualAlignmentDwellMs: [{code: 'visual_dwell_brief', levelKey: 'brief'}, {code: 'visual_dwell_typical', levelKey: 'typical'}, {code: 'visual_dwell_sustained', levelKey: 'sustained'}],
    nodPresent: [{code: 'nod_absent', levelKey: 'absent'}, {code: 'nod_observed', levelKey: 'observed'}],
    nodRateMin: [{code: 'nod_rate_low', levelKey: 'low'}, {code: 'nod_rate_typical', levelKey: 'typical'}, {code: 'nod_rate_high', levelKey: 'high'}],
    smileActivityRatio: [{code: 'smile_activity_absent', levelKey: 'absent'}, {code: 'smile_activity_sparse', levelKey: 'sparse'}, {code: 'smile_activity_moderate', levelKey: 'moderate'}, {code: 'smile_activity_frequent', levelKey: 'frequent'}],
    meanSmileActivation: [{code: 'smile_activation_subtle', levelKey: 'subtle'}, {code: 'smile_activation_typical', levelKey: 'typical'}, {code: 'smile_activation_marked', levelKey: 'marked'}],
  };

  // Render a base label value as its full ordered scale, highlighting the
  // observed level. When the label is unavailable, show a plain "No disponible".
  const renderScaleValue = (featureKey: string, label?: FamilyLabel): ReactNode => {
    const scale = levelScales[featureKey];
    const activeCode = label?.status === 'ok' ? label?.value ?? undefined : undefined;
    if (!scale || !activeCode) return observationUnavailable;
    return (
      <span className="turn-detail-scale">
        {scale.map(({code, levelKey}) => (
          <span
            key={code}
            className={code === activeCode ? 'turn-detail-scale-level is-active' : 'turn-detail-scale-level'}
          >
            {t(`clinicalChat.recap.levels.${levelKey}`)}
          </span>
        ))}
      </span>
    );
  };

  // Individual (base) label row: the left label stays, the value shows the
  // level scale with the observed level highlighted. No unit column.
  const renderBaseLabelRow = (labelKey: string, featureKey: string, label: FamilyLabel | undefined, key: string) => (
    <div className="turn-detail-row turn-detail-row--label" key={key}>
      <dt>{t(labelKey)}</dt>
      <dd className="turn-detail-label-value">{renderScaleValue(featureKey, label)}</dd>
    </div>
  );

  // Integrated label row: single localized value, no unit column.
  const renderLabelRow = (labelKey: string, label: FamilyLabel | undefined, key: string) => (
    <div className="turn-detail-row turn-detail-row--label" key={key}>
      <dt>{t(labelKey)}</dt>
      <dd className="turn-detail-label-value">{labelDisplay(label)}</dd>
    </div>
  );

  // The three ordered subgroups of a family: base features, then initial
  // (base) labels, then the integrated label. Each subgroup is its own
  // <dl className="turn-detail-subgroup">, and the separator line is drawn only
  // BETWEEN subgroups (see .turn-detail-subgroup + .turn-detail-subgroup in the
  // design system), not between individual rows.
  const renderFamily = (
    familyKey: string,
    metricRows: ReactNode[],
    baseLabels: Record<string, FamilyLabel> | undefined,
    baseLabelFeatures: {featureKey: string; labelKey: string}[],
    integratedLabel: FamilyLabel | undefined,
  ) => (
    <div className="turn-detail-group" key={familyKey}>
      <h5>{t(`clinicalChat.recap.families.${familyKey}`)}</h5>
      <dl className="turn-detail-subgroup">{metricRows}</dl>
      <dl className="turn-detail-subgroup">
        {baseLabelFeatures.map(({featureKey, labelKey}) =>
          renderBaseLabelRow(labelKey, featureKey, baseLabels?.[featureKey], `${familyKey}-base-${featureKey}`),
        )}
      </dl>
      <dl className="turn-detail-subgroup">
        {renderLabelRow('clinicalChat.recap.integratedLabel', integratedLabel, `${familyKey}-integrated`)}
      </dl>
    </div>
  );

  const paraverbal = detailTurn?.paraverbal?.processed;
  const paraverbalLabels = detailTurn?.paraverbal?.integratedLabels;
  const paraverbalBase = detailTurn?.paraverbal?.baseLabels;
  const nonverbal = detailTurn?.nonverbalFeatures?.processed;
  const nonverbalLabels = detailTurn?.nonverbalFeatures?.integratedLabels;
  const nonverbalBase = detailTurn?.nonverbalFeatures?.baseLabels;

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
                      disabled={infoDisabled}
                      className="mt-1.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-blue-700 disabled:cursor-not-allowed disabled:text-slate-300 disabled:hover:bg-transparent [&_svg]:h-4 [&_svg]:w-4"
                      aria-label={t('clinicalChat.recap.turnInfo')}
                      title={t('clinicalChat.recap.turnInfo')}
                    >
                      <Info color="currentColor" />
                    </button>
                    <button
                      type="button"
                      onClick={() => seekToTurn(turn)}
                      disabled={!hasMedia || typeof turn.startMs !== 'number'}
                      className={`min-w-0 flex-1 rounded-xl border p-3 text-left transition-colors enabled:cursor-pointer ${
                        isStudent
                          ? 'border-blue-100 bg-blue-50 enabled:hover:bg-blue-100'
                          : 'border-slate-200 bg-slate-100 enabled:hover:bg-slate-200'
                      } ${active ? 'ring-2 ring-blue-500 ring-offset-1' : ''}`}
                      title={
                        hasMedia && typeof turn.startMs === 'number'
                          ? t('clinicalChat.recap.jumpToTurn')
                          : undefined
                      }
                    >
                      <p className="whitespace-pre-wrap text-sm leading-5 text-slate-800">{turn.transcript}</p>
                      {typeof turn.startMs === 'number' && (
                        <span className="block text-right text-timestamp leading-none text-slate-400">{formatElapsed(turn.startMs / 1000)}</span>
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
                    <dt>{t('clinicalChat.recap.duration')}</dt>
                    <dd>{formatDuration(detailTurn.startMs, detailTurn.endMs) ?? t('clinicalChat.recap.notAvailable')}</dd>
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
                    {renderFamily(
                      'temporal',
                      [
                        renderMetricRow('clinicalChat.recap.metrics.speechRateWpm', paraverbal?.speechRateWpm, 'clinicalChat.recap.units.wordsPerMinute'),
                        renderMetricRow('clinicalChat.recap.metrics.articulationRateWpm', paraverbal?.articulationRateWpm, 'clinicalChat.recap.units.wordsPerMinute'),
                        renderMetricRow('clinicalChat.recap.metrics.pauseCount', paraverbal?.pauseCount, 'clinicalChat.recap.units.count'),
                        renderMetricRow('clinicalChat.recap.metrics.totalPauseDurationMs', paraverbal?.totalPauseDurationMs, 'clinicalChat.recap.units.milliseconds'),
                        renderMetricRow('clinicalChat.recap.metrics.medianPauseDurationMs', paraverbal?.medianPauseDurationMs, 'clinicalChat.recap.units.milliseconds'),
                        renderMetricRow('clinicalChat.recap.metrics.pauseTimeRatio', paraverbal?.pauseTimeRatio, 'clinicalChat.recap.units.ratio'),
                      ],
                      paraverbalBase?.temporal,
                      [
                        {featureKey: 'speechRateWpm', labelKey: 'clinicalChat.recap.baseLabels.speechRate'},
                        {featureKey: 'articulationRateWpm', labelKey: 'clinicalChat.recap.baseLabels.articulationRate'},
                        {featureKey: 'medianPauseDurationMs', labelKey: 'clinicalChat.recap.baseLabels.pauseDuration'},
                        {featureKey: 'pauseFrequencyPerMin', labelKey: 'clinicalChat.recap.baseLabels.pauseFrequency'},
                        {featureKey: 'pauseTimeRatio', labelKey: 'clinicalChat.recap.baseLabels.pauseLoad'},
                      ],
                      paraverbalLabels?.temporal,
                    )}
                    {renderFamily(
                      'prosodicLevel',
                      [
                        renderMetricRow('clinicalChat.recap.metrics.f0MedianSemitones', paraverbal?.f0MedianSemitones, 'clinicalChat.recap.units.semitones'),
                        renderMetricRow('clinicalChat.recap.metrics.medianLoudness', paraverbal?.medianLoudness, 'clinicalChat.recap.units.loudness'),
                      ],
                      paraverbalBase?.prosodicLevel,
                      [
                        {featureKey: 'relativePitchShiftSt', labelKey: 'clinicalChat.recap.baseLabels.relativePitch'},
                        {featureKey: 'medianLoudness', labelKey: 'clinicalChat.recap.baseLabels.loudnessLevel'},
                      ],
                      paraverbalLabels?.prosodicLevel,
                    )}
                    {renderFamily(
                      'prosodicModulation',
                      [
                        renderMetricRow('clinicalChat.recap.metrics.f0P20P80RangeSemitones', paraverbal?.f0P20P80RangeSemitones, 'clinicalChat.recap.units.semitones'),
                        renderMetricRow('clinicalChat.recap.metrics.loudnessP20P80Range', paraverbal?.loudnessP20P80Range, 'clinicalChat.recap.units.loudness'),
                      ],
                      paraverbalBase?.prosodicModulation,
                      [
                        {featureKey: 'f0P20P80RangeSemitones', labelKey: 'clinicalChat.recap.baseLabels.intonation'},
                        {featureKey: 'loudnessP20P80Range', labelKey: 'clinicalChat.recap.baseLabels.loudnessVariability'},
                      ],
                      paraverbalLabels?.prosodicModulation,
                    )}
                  </div>
                ) : (
                  <p className="turn-detail-empty">{t('clinicalChat.recap.paraverbalUnavailable')}</p>
                )}
              </section>

              <section className="turn-detail-column">
                <h4>{t('clinicalChat.recap.nonverbal')}</h4>
                {detailTurn.nonverbalFeatures ? (
                  <div className="turn-detail-groups">
                    {renderFamily(
                      'visualOrientation',
                      [
                        renderMetricRow('clinicalChat.recap.metrics.visualAlignmentRatio', nonverbal?.visualAlignmentRatio, 'clinicalChat.recap.units.ratio'),
                        renderMetricRow('clinicalChat.recap.metrics.medianVisualAlignmentDwellMs', nonverbal?.medianVisualAlignmentDwellMs, 'clinicalChat.recap.units.milliseconds'),
                      ],
                      nonverbalBase?.visualOrientation,
                      [
                        {featureKey: 'visualAlignmentRatio', labelKey: 'clinicalChat.recap.baseLabels.visualAlignment'},
                        {featureKey: 'medianVisualAlignmentDwellMs', labelKey: 'clinicalChat.recap.baseLabels.visualDwell'},
                      ],
                      nonverbalLabels?.visualOrientation,
                    )}
                    {renderFamily(
                      'headGesturalFeedback',
                      [
                        renderMetricRow('clinicalChat.recap.metrics.nodCount', nonverbal?.nodCount, 'clinicalChat.recap.units.count'),
                        renderMetricRow('clinicalChat.recap.metrics.nodRateMin', nonverbal?.nodRateMin, 'clinicalChat.recap.units.eventsPerMinute'),
                      ],
                      nonverbalBase?.headGesturalFeedback,
                      [
                        {featureKey: 'nodPresent', labelKey: 'clinicalChat.recap.baseLabels.nodPresence'},
                        {featureKey: 'nodRateMin', labelKey: 'clinicalChat.recap.baseLabels.nodRate'},
                      ],
                      nonverbalLabels?.headGesturalFeedback,
                    )}
                    {renderFamily(
                      'facialExpressivity',
                      [
                        renderMetricRow('clinicalChat.recap.metrics.smileActivityRatio', nonverbal?.smileActivityRatio, 'clinicalChat.recap.units.ratio'),
                        renderMetricRow('clinicalChat.recap.metrics.meanSmileActivation', nonverbal?.meanSmileActivation, 'clinicalChat.recap.units.auActivation'),
                      ],
                      nonverbalBase?.facialExpressivity,
                      [
                        {featureKey: 'smileActivityRatio', labelKey: 'clinicalChat.recap.baseLabels.smileActivity'},
                        {featureKey: 'meanSmileActivation', labelKey: 'clinicalChat.recap.baseLabels.smileActivation'},
                      ],
                      nonverbalLabels?.facialExpressivity,
                    )}
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

