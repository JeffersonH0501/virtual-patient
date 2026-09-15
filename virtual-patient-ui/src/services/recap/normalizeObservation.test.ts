import {describe, expect, it} from 'vitest';

import {NonverbalObservation, ParaverbalObservation} from '../../types/recording';
import {
  normalizeNonverbalObservation,
  normalizeParaverbalObservation,
} from './normalizeObservation';

// Tests for the frontend compatibility adapter (task 9.3; Requirements 28.7,
// 22.2). They verify that a raw LEGACY flat observation renders through the
// same layered read view the UI expects, without fabricating any label the
// legacy data never computed, and that already-layered payloads pass through
// unchanged.
//
// Casing note: the recordings service runs `transformToCamelCase` over the raw
// API JSON before observations reach the adapter, so a legacy flat payload
// arrives with camelCased keys (`speech_rate_wpm` -> `speechRateWpm`,
// `interpretability.acoustic_temporal.labels.values.temporal_profile` ->
// `interpretability.acousticTemporal.labels.values.temporalProfile`). The
// fixtures below use the already-camelCased shape the adapter operates on.
//
// The observations are typed loosely because a legacy flat payload does not
// match the layered type surface; casting through `unknown` mirrors how the
// recordings service hands these objects to the adapter at runtime.
const asParaverbal = (payload: Record<string, unknown>): ParaverbalObservation =>
  payload as unknown as ParaverbalObservation;
const asNonverbal = (payload: Record<string, unknown>): NonverbalObservation =>
  payload as unknown as NonverbalObservation;

describe('normalizeParaverbalObservation', () => {
  it('wraps a legacy flat payload with a temporalProfile into the layered view', () => {
    const legacy = asParaverbal({
      speechRateWpm: 142,
      articulationRateWpm: 165,
      pauseTimeRatio: 0.22,
      medianPauseDurationMs: 340,
      audioQuality: {validRatio: 0.91, issues: []},
      interpretability: {
        acousticTemporal: {
          labels: {
            status: 'ok',
            values: {temporalProfile: 'measured_pace'},
          },
          calibration: {reference: 'session'},
          scope: {context: 'speaking'},
        },
      },
    });

    const result = normalizeParaverbalObservation(legacy);

    expect(result).not.toBeNull();
    expect(result?.schema).toBe('legacy');
    expect(result?.modality).toBe('paraverbal');

    // The flat metrics move into the `processed` layer verbatim; nothing is
    // invented and `raw` / `baseLabels` stay null for legacy rows.
    expect(result?.processed?.speechRateWpm).toBe(142);
    expect(result?.processed?.articulationRateWpm).toBe(165);
    expect(result?.processed?.pauseTimeRatio).toBe(0.22);
    expect(result?.processed?.medianPauseDurationMs).toBe(340);
    expect(result?.raw).toBeNull();
    expect(result?.baseLabels).toBeNull();
    expect(result?.versions).toBeNull();
    expect(result?.configHash).toBeNull();

    // The only genuinely computed legacy integrated label is `temporal`; it
    // carries the stored temporalProfile value.
    expect(result?.integratedLabels?.temporal?.status).toBe('ok');
    expect(result?.integratedLabels?.temporal?.value).toBe('measured_pace');
    expect(result?.integratedLabels?.temporal?.reason).toBeNull();

    // Prosodic families were never computed by the legacy shape, so they are
    // surfaced as unavailable with a null value, never fabricated.
    expect(result?.integratedLabels?.prosodicLevel?.status).toBe('unavailable');
    expect(result?.integratedLabels?.prosodicLevel?.value).toBeNull();
    expect(result?.integratedLabels?.prosodicLevel?.reason).toBe('feature_unavailable');
    expect(result?.integratedLabels?.prosodicModulation?.status).toBe('unavailable');
    expect(result?.integratedLabels?.prosodicModulation?.value).toBeNull();
    expect(result?.integratedLabels?.prosodicModulation?.reason).toBe('feature_unavailable');

    // Context is resolved from the legacy temporal scope when no top-level
    // context is present, and the original interpretability block is kept.
    expect(result?.context).toBe('speaking');
    expect(result?.legacyInterpretability).toEqual(legacy.interpretability);
  });

  it('reports the temporal family unavailable when legacy data has no temporalProfile', () => {
    const legacy = asParaverbal({
      speechRateWpm: 120,
      audioQuality: {validRatio: 0.8, issues: []},
      // interpretability present but without a computed temporalProfile.
      interpretability: {
        acousticTemporal: {
          labels: {status: 'unavailable', values: {}},
        },
      },
    });

    const result = normalizeParaverbalObservation(legacy);

    expect(result?.schema).toBe('legacy');
    expect(result?.processed?.speechRateWpm).toBe(120);
    expect(result?.integratedLabels?.temporal?.status).toBe('unavailable');
    expect(result?.integratedLabels?.temporal?.value).toBeNull();
    expect(result?.integratedLabels?.temporal?.reason).toBe('feature_unavailable');
  });

  it('returns an already-layered paraverbal payload unchanged (pass-through)', () => {
    const layered = {
      schema: 'layered',
      modality: 'paraverbal',
      processed: {speechRateWpm: 150},
      integratedLabels: {temporal: {status: 'ok', value: 'measured_pace'}},
      versions: {processing: '1', thresholds: '1', label_rules: '1'},
      configHash: 'abc123',
    } as unknown as ParaverbalObservation;

    const result = normalizeParaverbalObservation(layered);

    // Not re-wrapped: same reference and untouched fields.
    expect(result).toBe(layered);
    expect(result?.schema).toBe('layered');
    expect(result?.configHash).toBe('abc123');
  });

  it('maps null and undefined to null', () => {
    expect(normalizeParaverbalObservation(null)).toBeNull();
    expect(normalizeParaverbalObservation(undefined)).toBeNull();
  });
});

describe('normalizeNonverbalObservation', () => {
  it('wraps a legacy flat payload and reports every nonverbal family unavailable', () => {
    const legacy = asNonverbal({
      visualAlignmentRatio: 0.64,
      smileActivityRatio: 0.18,
      nodCount: 3,
      videoQuality: {sampledFrameCount: 120, validFrameCount: 110, issues: []},
      observationContext: 'listening',
    });

    const result = normalizeNonverbalObservation(legacy);

    expect(result).not.toBeNull();
    expect(result?.schema).toBe('legacy');
    expect(result?.modality).toBe('nonverbal');

    // Flat metrics move into `processed`; raw/baseLabels/versions stay null.
    expect(result?.processed?.visualAlignmentRatio).toBe(0.64);
    expect(result?.processed?.smileActivityRatio).toBe(0.18);
    expect(result?.processed?.nodCount).toBe(3);
    expect(result?.raw).toBeNull();
    expect(result?.baseLabels).toBeNull();
    expect(result?.versions).toBeNull();
    expect(result?.configHash).toBeNull();

    // The legacy flat shape never produced any nonverbal integrated label, so
    // all three families are unavailable with a null value.
    expect(result?.integratedLabels?.visualOrientation?.status).toBe('unavailable');
    expect(result?.integratedLabels?.visualOrientation?.value).toBeNull();
    expect(result?.integratedLabels?.visualOrientation?.reason).toBe('feature_unavailable');
    expect(result?.integratedLabels?.headGesturalFeedback?.status).toBe('unavailable');
    expect(result?.integratedLabels?.headGesturalFeedback?.value).toBeNull();
    expect(result?.integratedLabels?.headGesturalFeedback?.reason).toBe('feature_unavailable');
    expect(result?.integratedLabels?.facialExpressivity?.status).toBe('unavailable');
    expect(result?.integratedLabels?.facialExpressivity?.value).toBeNull();
    expect(result?.integratedLabels?.facialExpressivity?.reason).toBe('feature_unavailable');

    // Context is read from the legacy `observationContext` field.
    expect(result?.context).toBe('listening');
  });

  it('returns an already-layered nonverbal payload unchanged (pass-through)', () => {
    const layered = {
      schema: 'layered',
      modality: 'nonverbal',
      processed: {visualAlignmentRatio: 0.7},
      integratedLabels: {visualOrientation: {status: 'ok', value: 'oriented'}},
      configHash: 'def456',
    } as unknown as NonverbalObservation;

    const result = normalizeNonverbalObservation(layered);

    expect(result).toBe(layered);
    expect(result?.schema).toBe('layered');
    expect(result?.configHash).toBe('def456');
  });

  it('maps null and undefined to null', () => {
    expect(normalizeNonverbalObservation(null)).toBeNull();
    expect(normalizeNonverbalObservation(undefined)).toBeNull();
  });
});
