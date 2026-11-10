import {ReactNode} from 'react';
import {useTranslation} from 'react-i18next';
import {FamilyLabel, RecapTurn} from '../../types/recording';
import {formatPlaybackTime} from '../../utils/duration';

const formatTimestamp = (milliseconds?: number | null): string | null => {
  if (typeof milliseconds !== 'number' || !Number.isFinite(milliseconds) || milliseconds < 0) return null;
  return `${formatPlaybackTime(milliseconds / 1000)} (${milliseconds} ms)`;
};

// Total elapsed time of a turn (end - start), rendered like a timestamp with an
// exact millisecond value. Returns null unless both bounds are numeric and the
// span is non-negative, so a fabricated or malformed window is shown as "not
// available" rather than a misleading duration.
const formatTurnDuration = (startMs?: number | null, endMs?: number | null): string | null => {
  if (typeof startMs !== 'number' || typeof endMs !== 'number') return null;
  const durationMs = endMs - startMs;
  if (durationMs < 0) return null;
  return formatTimestamp(durationMs);
};

const formatMetricValue = (value?: number | null): string | null => {
  if (typeof value !== 'number') return null;
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
};

export const TurnEvidenceDetails = ({turn: detailTurn}: {turn: RecapTurn}) => {
  const {t} = useTranslation();
  const observationUnavailable = t('clinicalChat.recap.notAvailable');

  const renderMetricRow = (labelKey: string, value?: number | null, unitKey?: string) => (
    <div className="turn-detail-row" key={labelKey}>
      <dt>{t(labelKey)}</dt>
      <dd>{formatMetricValue(value) ?? observationUnavailable}</dd>
      <span>{unitKey && typeof value === 'number' ? t(unitKey) : ''}</span>
    </div>
  );

  // Localize a base/integrated label VALUE (e.g. `sustained_gaze_orientation`)
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
    speechRateWpm: [
      {code: 'speech_rate_low', levelKey: 'low'},
      {code: 'speech_rate_typical', levelKey: 'typical'},
      {code: 'speech_rate_high', levelKey: 'high'},
    ],
    articulationRateWpm: [
      {code: 'articulation_rate_low', levelKey: 'low'},
      {code: 'articulation_rate_typical', levelKey: 'typical'},
      {code: 'articulation_rate_high', levelKey: 'high'},
    ],
    medianPauseDurationMs: [
      {code: 'pause_duration_brief', levelKey: 'brief'},
      {code: 'pause_duration_typical', levelKey: 'typical'},
      {code: 'pause_duration_long', levelKey: 'long'},
    ],
    pauseFrequencyPerMin: [
      {code: 'pause_frequency_low', levelKey: 'low'},
      {code: 'pause_frequency_typical', levelKey: 'typical'},
      {code: 'pause_frequency_high', levelKey: 'high'},
    ],
    pauseTimeRatio: [
      {code: 'pause_load_low', levelKey: 'low'},
      {code: 'pause_load_typical', levelKey: 'typical'},
      {code: 'pause_load_high', levelKey: 'high'},
    ],
    medianLoudness: [
      {code: 'loudness_low', levelKey: 'low'},
      {code: 'loudness_typical', levelKey: 'typical'},
      {code: 'loudness_high', levelKey: 'high'},
    ],
    f0P20P80RangeSemitones: [
      {code: 'f0_variability_reduced', levelKey: 'low'},
      {code: 'f0_variability_typical', levelKey: 'typical'},
      {code: 'f0_variability_high', levelKey: 'high'},
    ],
    loudnessP20P80Range: [
      {code: 'loudness_variability_low', levelKey: 'low'},
      {code: 'loudness_variability_typical', levelKey: 'typical'},
      {code: 'loudness_variability_high', levelKey: 'high'},
    ],
    interactionGazeRatio: [
      {code: 'interaction_gaze_outside', levelKey: 'outside'},
      {code: 'interaction_gaze_inside', levelKey: 'inside'},
    ],
    nodPresent: [
      {code: 'nod_absent', levelKey: 'absent'},
      {code: 'nod_observed', levelKey: 'observed'},
    ],
    smileActivityRatio: [
      {code: 'smile_activity_absent', levelKey: 'absent'},
      {code: 'smile_activity_sparse', levelKey: 'sparse'},
      {code: 'smile_activity_moderate', levelKey: 'moderate'},
      {code: 'smile_activity_frequent', levelKey: 'frequent'},
    ],
  };

  // Render a base label value as its full ordered scale, highlighting the
  // observed level. When the label is unavailable, show a plain "No disponible".
  const renderScaleValue = (featureKey: string, label?: FamilyLabel): ReactNode => {
    const scale = levelScales[featureKey];
    const activeCode = label?.status === 'ok' ? (label?.value ?? undefined) : undefined;
    if (!scale || !activeCode) return observationUnavailable;
    return (
      <span className="turn-detail-scale">
        {scale.map(({code, levelKey}) => (
          <span
            key={code}
            className={
              code === activeCode ? 'turn-detail-scale-level is-active' : 'turn-detail-scale-level'
            }
          >
            {t(`clinicalChat.recap.levels.${levelKey}`)}
          </span>
        ))}
      </span>
    );
  };

  // Individual (base) label row: the left label stays, the value shows the
  // level scale with the observed level highlighted. No unit column.
  const renderBaseLabelRow = (
    labelKey: string,
    featureKey: string,
    label: FamilyLabel | undefined,
    key: string,
  ) => (
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
      <h4>{t(`clinicalChat.recap.families.${familyKey}`)}</h4>
      <dl className="turn-detail-subgroup">{metricRows}</dl>
      <dl className="turn-detail-subgroup">
        {baseLabelFeatures.map(({featureKey, labelKey}) =>
          renderBaseLabelRow(
            labelKey,
            featureKey,
            baseLabels?.[featureKey],
            `${familyKey}-base-${featureKey}`,
          ),
        )}
      </dl>
      <dl className="turn-detail-subgroup">
        {renderLabelRow(
          'clinicalChat.recap.integratedLabel',
          integratedLabel,
          `${familyKey}-integrated`,
        )}
      </dl>
    </div>
  );

  const paraverbal = detailTurn?.paraverbal?.processed;
  const paraverbalLabels = detailTurn?.paraverbal?.integratedLabels;
  const paraverbalBase = detailTurn?.paraverbal?.baseLabels;
  const nonverbal = detailTurn?.nonverbalFeatures?.processed;
  const nonverbalLabels = detailTurn?.nonverbalFeatures?.integratedLabels;
  const nonverbalBase = detailTurn?.nonverbalFeatures?.baseLabels;
  const gazeObservations = detailTurn.nonverbalFeatures?.raw?.gazeObservations;
  const gazeOutsideCalibration = nonverbal?.interactionGazeRatio == null && (
    nonverbalBase?.gazeOrientation?.visualAlignmentRatio?.reason === 'outside_calibrated_geometry' ||
    (Array.isArray(gazeObservations) && gazeObservations.length > 0 &&
      gazeObservations.filter((observation) => observation?.state === 'outside_calibrated_geometry').length > gazeObservations.length / 2)
  );

  return (
    <div className="turn-detail-content">
      <section className="turn-detail-column turn-detail-overview dialog-reading-card">
        <h3>{t('clinicalChat.recap.generalInformation')}</h3>
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
            <dd>
              {formatTurnDuration(detailTurn.startMs, detailTurn.endMs) ??
                t('clinicalChat.recap.notAvailable')}
            </dd>
          </div>
          <div className="turn-detail-general-item">
            <dt>{t('clinicalChat.recap.transcript')}</dt>
            <dd>{detailTurn.transcript || t('clinicalChat.recap.notAvailable')}</dd>
          </div>
        </dl>
      </section>

      <section className="turn-detail-column dialog-reading-card">
        <h3>{t('clinicalChat.recap.paraverbal')}</h3>
        {detailTurn.paraverbal ? (
          <div className="turn-detail-groups">
            {renderFamily(
              'speechTiming',
              [
                renderMetricRow(
                  'clinicalChat.recap.metrics.speechRateWpm',
                  paraverbal?.speechRateWpm,
                  'clinicalChat.recap.units.wordsPerMinute',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.articulationRateWpm',
                  paraverbal?.articulationRateWpm,
                  'clinicalChat.recap.units.wordsPerMinute',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.pauseCount',
                  paraverbal?.pauseCount,
                  'clinicalChat.recap.units.count',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.totalPauseDurationMs',
                  paraverbal?.totalPauseDurationMs,
                  'clinicalChat.recap.units.milliseconds',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.medianPauseDurationMs',
                  paraverbal?.medianPauseDurationMs,
                  'clinicalChat.recap.units.milliseconds',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.pauseTimeRatio',
                  paraverbal?.pauseTimeRatio,
                  'clinicalChat.recap.units.ratio',
                ),
              ],
              paraverbalBase?.speechTiming,
              [
                {
                  featureKey: 'speechRateWpm',
                  labelKey: 'clinicalChat.recap.baseLabels.speechRate',
                },
                {
                  featureKey: 'articulationRateWpm',
                  labelKey: 'clinicalChat.recap.baseLabels.articulationRate',
                },
                {
                  featureKey: 'medianPauseDurationMs',
                  labelKey: 'clinicalChat.recap.baseLabels.pauseDuration',
                },
                {
                  featureKey: 'pauseFrequencyPerMin',
                  labelKey: 'clinicalChat.recap.baseLabels.pauseFrequency',
                },
                {
                  featureKey: 'pauseTimeRatio',
                  labelKey: 'clinicalChat.recap.baseLabels.pauseLoad',
                },
              ],
              paraverbalLabels?.speechTiming,
            )}
            {renderFamily(
              'prosodicLevel',
              [
                renderMetricRow(
                  'clinicalChat.recap.metrics.f0MedianSemitones',
                  paraverbal?.f0MedianSemitones,
                  'clinicalChat.recap.units.semitones',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.medianLoudness',
                  paraverbal?.medianLoudness,
                  'clinicalChat.recap.units.loudness',
                ),
              ],
              paraverbalBase?.prosodicLevel,
              [
                {
                  featureKey: 'medianLoudness',
                  labelKey: 'clinicalChat.recap.baseLabels.loudnessLevel',
                },
              ],
              paraverbalLabels?.prosodicLevel,
            )}
            {renderFamily(
              'prosodicVariability',
              [
                renderMetricRow(
                  'clinicalChat.recap.metrics.f0P20P80RangeSemitones',
                  paraverbal?.f0P20P80RangeSemitones,
                  'clinicalChat.recap.units.semitones',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.loudnessP20P80Range',
                  paraverbal?.loudnessP20P80Range,
                  'clinicalChat.recap.units.loudness',
                ),
              ],
              paraverbalBase?.prosodicVariability,
              [
                {
                  featureKey: 'f0P20P80RangeSemitones',
                  labelKey: 'clinicalChat.recap.baseLabels.intonation',
                },
                {
                  featureKey: 'loudnessP20P80Range',
                  labelKey: 'clinicalChat.recap.baseLabels.loudnessVariability',
                },
              ],
              paraverbalLabels?.prosodicVariability,
            )}
          </div>
        ) : (
          <p className="turn-detail-empty">{t('clinicalChat.recap.paraverbalUnavailable')}</p>
        )}
      </section>

      <section className="turn-detail-column dialog-reading-card">
        <h3>{t('clinicalChat.recap.nonverbal')}</h3>
        {gazeOutsideCalibration && (
          <p className="turn-detail-empty">{t('clinicalChat.recap.gazeOutsideCalibration')}</p>
        )}
        {detailTurn.nonverbalFeatures ? (
          <div className="turn-detail-groups">
            {renderFamily(
              'gazeOrientation',
              [
                renderMetricRow(
                  'clinicalChat.recap.metrics.visualAlignmentRatio',
                  nonverbal?.interactionGazeRatio,
                  'clinicalChat.recap.units.ratio',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.medianVisualAlignmentDwellMs',
                  nonverbal?.medianInteractionDwellMs,
                  'clinicalChat.recap.units.milliseconds',
                ),
              ],
              nonverbalBase?.gazeOrientation,
              [
                {
                  featureKey: 'interactionGazeRatio',
                  labelKey: 'clinicalChat.recap.baseLabels.visualAlignment',
                },
              ],
              nonverbalLabels?.gazeOrientation,
            )}
            {renderFamily(
              'headNods',
              [
                renderMetricRow(
                  'clinicalChat.recap.metrics.nodCount',
                  nonverbal?.nodCount,
                  'clinicalChat.recap.units.count',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.nodRateMin',
                  nonverbal?.nodRateMin,
                  'clinicalChat.recap.units.eventsPerMinute',
                ),
              ],
              nonverbalBase?.headNods,
              [
                {
                  featureKey: 'nodPresent',
                  labelKey: 'clinicalChat.recap.baseLabels.nodPresence',
                },
              ],
              nonverbalLabels?.headNods,
            )}
            {renderFamily(
              'smileActivity',
              [
                renderMetricRow(
                  'clinicalChat.recap.metrics.smileActivityRatio',
                  nonverbal?.smileActivityRatio,
                  'clinicalChat.recap.units.ratio',
                ),
                renderMetricRow(
                  'clinicalChat.recap.metrics.meanSmileActivation',
                  nonverbal?.meanSmileActivation,
                  'clinicalChat.recap.units.auActivation',
                ),
              ],
              nonverbalBase?.smileActivity,
              [
                {
                  featureKey: 'smileActivityRatio',
                  labelKey: 'clinicalChat.recap.baseLabels.smileActivity',
                },
              ],
              nonverbalLabels?.smileActivity,
            )}
          </div>
        ) : (
          <p className="turn-detail-empty">{t('clinicalChat.recap.nonverbalUnavailable')}</p>
        )}
      </section>
    </div>
  );
};
