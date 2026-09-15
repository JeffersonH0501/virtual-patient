import {
  FamilyLabel,
  NonverbalIntegratedLabels,
  NonverbalObservation,
  NonverbalProcessed,
  ParaverbalIntegratedLabels,
  ParaverbalObservation,
  ParaverbalProcessed,
} from '../../types/recording';

// Frontend compatibility adapter for per-turn multimodal observations
// (Requirements 22.2, 23.2; design section "Backward compatibility &
// cross-codebase references", Property 15).
//
// The recap endpoint already normalizes stored rows into the layered read shape
// through the backend adapter (`app/multimodal/legacy_adapter.py`, task 8.2), so
// most payloads reach the UI already layered. This module is the defensive
// frontend counterpart: it guarantees that even a raw legacy flat observation
// that never passed through the backend normalizer (schema absent, only old
// top-level fields such as `speechRateWpm` / `visualAlignmentRatio` /
// `interpretability`) is rendered through the same layered view the UI expects.
//
// It mirrors the backend `legacy_adapter.py` mapping exactly:
//   - Legacy paraverbal: the only genuinely computed integrated label is
//     `temporal`, taken from `interpretability.acousticTemporal.labels.values
//     .temporalProfile`. `prosodicLevel` / `prosodicModulation` were never
//     computed and are surfaced as unavailable (`feature_unavailable`).
//   - Legacy nonverbal: no nonverbal integrated label was ever computed, so all
//     three families are surfaced as unavailable.
//
// The functions are pure and read-only: they never mutate the input and never
// fabricate a label for a family the legacy data did not compute (Requirement
// 22.3 non-destructive, descriptive-only). `null` / `undefined` map to `null`.
//
// NOTE ON CASING: the recordings service runs `transformToCamelCase` over the
// raw API JSON before these observations are typed, so this adapter operates on
// the already-camelCased read view. A raw legacy flat payload therefore arrives
// with camelCased keys (`speech_rate_wpm` -> `speechRateWpm`,
// `interpretability.acoustic_temporal.labels.values.temporal_profile` ->
// `interpretability.acousticTemporal.labels.values.temporalProfile`).

const SCHEMA_LEGACY = 'legacy' as const;

// Reason mirrored from the backend `UnavailableReason` enum for families the
// legacy flat shape never computed.
const FEATURE_UNAVAILABLE = 'feature_unavailable';

// Keys that unambiguously identify an already-layered observation. Legacy flat
// payloads never carry these (their metrics sit at the top level). This matches
// the backend `is_layered` detection contract (design: "if processed /
// integrated_labels keys exist it is layered").
const LAYERED_MARKER_KEYS = ['processed', 'integratedLabels'] as const;

// Legacy paraverbal metric keys that belong in the `processed` layer once the
// flat payload is wrapped. Everything except the structural/quality/context
// keys is preserved verbatim, so this list is the allow-list of derived metrics
// surfaced through `ParaverbalProcessed`.
const PARAVERBAL_PROCESSED_KEYS: (keyof ParaverbalProcessed)[] = [
  'speechRateWpm',
  'articulationRateWpm',
  'pauseCount',
  'totalPauseDurationMs',
  'medianPauseDurationMs',
  'pauseFrequencyPerMin',
  'pauseTimeRatio',
  'medianLoudness',
  'f0MedianSemitones',
  'f0P20P80RangeSemitones',
  'loudnessP20P80Range',
  'relativePitchShiftSt',
];

const NONVERBAL_PROCESSED_KEYS: (keyof NonverbalProcessed)[] = [
  'visualAlignmentRatio',
  'medianVisualAlignmentDwellMs',
  'nodCount',
  'nodRateMin',
  'smileActivityRatio',
  'meanSmileActivation',
  'context',
];

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

// A payload is layered when it already carries a `processed` or
// `integratedLabels` key (whether produced by the pipeline or by the backend
// adapter). Everything else is treated as a legacy flat payload.
const isLayered = (payload: UnknownRecord): boolean =>
  LAYERED_MARKER_KEYS.some((key) => key in payload);

// An `unavailable` family label carrying an explanation but no value, so no
// label is fabricated for a family the legacy data never computed.
const unavailableFamily = (reason: string = FEATURE_UNAVAILABLE): FamilyLabel => ({
  status: 'unavailable',
  value: null,
  reason,
  evidence: {},
});

// Surface the legacy `temporalProfile` as the `temporal` integrated label. The
// legacy paraverbal payload stored the only genuinely computed integrated label
// at `interpretability.acousticTemporal.labels.values.temporalProfile`. When
// present it is surfaced with the supporting legacy label values kept as
// evidence; when absent the family is reported unavailable, never invented.
const legacyTemporalLabel = (payload: UnknownRecord): FamilyLabel => {
  const interpretability = payload.interpretability;
  if (!isRecord(interpretability)) return unavailableFamily();
  const block = interpretability.acousticTemporal;
  if (!isRecord(block)) return unavailableFamily();
  const labels = block.labels;
  const values = isRecord(labels) ? labels.values : undefined;
  if (!isRecord(values)) return unavailableFamily();
  const temporalProfile = values.temporalProfile;
  if (temporalProfile === null || temporalProfile === undefined) {
    return unavailableFamily();
  }
  return {
    status: 'ok',
    value: typeof temporalProfile === 'string' ? temporalProfile : String(temporalProfile),
    reason: null,
    // Keep the legacy sub-labels and calibration marker as evidence so the
    // origin of the label stays traceable; this is genuine legacy data.
    evidence: {
      source: SCHEMA_LEGACY,
      labels: values,
      calibration: block.calibration ?? null,
      labelsStatus: isRecord(labels) ? labels.status ?? null : null,
    },
  };
};

// Pick the known derived-metric keys from a flat payload into a typed
// `processed` layer. Only recognized keys are surfaced; `raw` stays null for
// legacy rows, matching the backend adapter which never reconstructs a raw
// layer from a flat legacy payload.
const pickProcessed = <T extends object>(
  payload: UnknownRecord,
  keys: (keyof T)[],
): T => {
  const processed: UnknownRecord = {};
  for (const key of keys) {
    const name = key as string;
    if (name in payload) processed[name] = payload[name];
  }
  return processed as T;
};

const normalizeLegacyParaverbal = (payload: UnknownRecord): ParaverbalObservation => {
  const integratedLabels: ParaverbalIntegratedLabels = {
    temporal: legacyTemporalLabel(payload),
    prosodicLevel: unavailableFamily(),
    prosodicModulation: unavailableFamily(),
  };

  // Resolve interaction context: prefer an explicit top-level `context`, then
  // fall back to the legacy temporal block's scope context when available.
  let context: string | null = null;
  if (typeof payload.context === 'string') {
    context = payload.context;
  } else {
    const interpretability = payload.interpretability;
    if (isRecord(interpretability)) {
      const block = interpretability.acousticTemporal;
      if (isRecord(block) && isRecord(block.scope) && typeof block.scope.context === 'string') {
        context = block.scope.context;
      }
    }
  }

  return {
    schema: SCHEMA_LEGACY,
    modality: 'paraverbal',
    raw: null,
    processed: pickProcessed<ParaverbalProcessed>(payload, PARAVERBAL_PROCESSED_KEYS),
    baseLabels: null,
    integratedLabels,
    quality: isRecord(payload.audioQuality) ? payload.audioQuality : {},
    versions: null,
    configHash: null,
    status: 'ok',
    reason: null,
    legacyInterpretability: isRecord(payload.interpretability) ? payload.interpretability : null,
    context,
  };
};

const normalizeLegacyNonverbal = (payload: UnknownRecord): NonverbalObservation => {
  const integratedLabels: NonverbalIntegratedLabels = {
    visualOrientation: unavailableFamily(),
    headGesturalFeedback: unavailableFamily(),
    facialExpressivity: unavailableFamily(),
  };
  return {
    schema: SCHEMA_LEGACY,
    modality: 'nonverbal',
    raw: null,
    processed: pickProcessed<NonverbalProcessed>(payload, NONVERBAL_PROCESSED_KEYS),
    baseLabels: null,
    integratedLabels,
    quality: isRecord(payload.videoQuality) ? payload.videoQuality : {},
    versions: null,
    configHash: null,
    status: 'ok',
    reason: null,
    context: typeof payload.observationContext === 'string'
      ? payload.observationContext
      : (typeof payload.context === 'string' ? payload.context : null),
  };
};

/**
 * Normalize a per-turn paraverbal observation into the layered read view.
 *
 * Already-layered payloads (produced by the pipeline or the backend adapter)
 * are returned as-is; a raw legacy flat payload is wrapped so `processed` holds
 * the derived metrics and `integratedLabels.temporal` reflects the genuine
 * legacy `temporalProfile` while the other families are reported unavailable.
 * `null` / `undefined` map to `null`.
 */
export const normalizeParaverbalObservation = (
  obs?: ParaverbalObservation | null,
): ParaverbalObservation | null => {
  if (obs === null || obs === undefined) return null;
  if (!isRecord(obs)) return null;
  if (isLayered(obs)) return obs;
  return normalizeLegacyParaverbal(obs);
};

/**
 * Normalize a per-turn nonverbal observation into the layered read view.
 *
 * Already-layered payloads are returned as-is; a raw legacy flat payload is
 * wrapped so `processed` holds the derived metrics and every nonverbal family
 * is reported unavailable, because the legacy flat shape never produced
 * nonverbal integrated labels. `null` / `undefined` map to `null`.
 */
export const normalizeNonverbalObservation = (
  obs?: NonverbalObservation | null,
): NonverbalObservation | null => {
  if (obs === null || obs === undefined) return null;
  if (!isRecord(obs)) return null;
  if (isLayered(obs)) return obs;
  return normalizeLegacyNonverbal(obs);
};
