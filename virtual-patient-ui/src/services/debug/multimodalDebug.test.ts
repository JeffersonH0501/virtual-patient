import {beforeEach, describe, expect, it, vi} from 'vitest';

import type {
  DebugUnavailable,
  OpenSmileFrameDebug,
  PyFeatFrameDebug,
} from './multimodalDebug';

// Tests for the DEV/DEBUG-ONLY multimodal debug service. Two layers:
//   1. `isDebugUnavailable` type guard - a pure function, no mocking needed.
//   2. `postDebugFrame` request handling - the 503 -> DebugUnavailable branch
//      and the ok -> camelCase branch, driven by a mocked `apiFetch`.
//
// Runner note: this project has no test runner installed yet (no vitest/jest
// dependency), and `tsconfig.app.json` excludes `src/**/*.test.ts` from the
// production build. Following the existing precedent
// (`src/services/recap/normalizeObservation.test.ts`), these are authored in
// vitest style so they run unchanged once vitest is added, and they type-check
// against the real exports.

// The transport dependencies are mocked so no real network call is made and
// the auth-header/URL modules do not need a browser environment.
const apiFetchMock = vi.fn();

vi.mock('../../utils/apiFetch', () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));
vi.mock('../../utils/request', () => ({API_URL: 'http://test.local'}));
vi.mock('../auth/authHeaders', () => ({getAuthHeaders: () => ({Authorization: 'Bearer test'})}));

// Imported after the mocks are registered so the module picks up the doubles.
import {isDebugUnavailable, postDebugFrame} from './multimodalDebug';

describe('isDebugUnavailable', () => {
  it('returns true for an unavailable body', () => {
    const value: DebugUnavailable = {available: false, reason: 'pyfeat_unavailable'};
    expect(isDebugUnavailable(value)).toBe(true);
  });

  it('returns false for a real Py-Feat observation', () => {
    const observation = {
      faceDetected: true,
      faceScore: 0.99,
      gazeYaw: null,
      gazePitch: null,
      headYaw: null,
      headPitch: null,
      headRoll: null,
      au12: null,
      landmarks: null,
      imageWidth: 640,
      imageHeight: 480,
      frameTimestampMs: null,
      processingMs: 12,
      extractor: {name: 'py-feat', version: '2.1.1', detector: 'Detectorv2'},
      reasons: {},
    } satisfies PyFeatFrameDebug;

    expect(isDebugUnavailable(observation)).toBe(false);
  });

  it('returns false for a real OpenSMILE observation', () => {
    const observation = {
      f0Semitones: 12.3,
      loudness: 0.4,
      voicing: 0.8,
      voicingKind: 'hnr_dbacf',
      featureNames: {f0: 'F0semitone', loudness: 'Loudness', voicing: 'HNRdBACF'},
      featureSet: 'eGeMAPSv02',
      frameTimestampMs: null,
      processingMs: 8,
      reasons: {},
    } satisfies OpenSmileFrameDebug;

    expect(isDebugUnavailable(observation)).toBe(false);
  });
});

describe('postDebugFrame', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it('returns a DebugUnavailable body when the backend responds 503', async () => {
    apiFetchMock.mockResolvedValue({
      status: 503,
      ok: false,
      json: async () => ({available: false, reason: 'pyfeat_unavailable'}),
    });

    const result = await postDebugFrame(new Blob(['x']), 1234);

    expect(isDebugUnavailable(result)).toBe(true);
    expect(result).toEqual({available: false, reason: 'pyfeat_unavailable'});
  });

  it('defaults the reason to "unavailable" when a 503 body lacks one', async () => {
    apiFetchMock.mockResolvedValue({
      status: 503,
      ok: false,
      json: async () => ({}),
    });

    const result = (await postDebugFrame(new Blob(['x']), 1)) as DebugUnavailable;

    expect(result.available).toBe(false);
    expect(result.reason).toBe('unavailable');
  });

  it('camelCases the snake_case backend payload on an ok response', async () => {
    apiFetchMock.mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({
        face_detected: true,
        face_score: 0.87,
        image_width: 640,
        image_height: 480,
        processing_ms: 15,
        extractor: {name: 'py-feat', version: '2.1.1', detector: 'Detectorv2'},
        reasons: {},
      }),
    });

    const result = await postDebugFrame(new Blob(['x']), 42);

    expect(isDebugUnavailable(result)).toBe(false);
    const frame = result as PyFeatFrameDebug;
    expect(frame.faceDetected).toBe(true);
    expect(frame.faceScore).toBe(0.87);
    expect(frame.imageWidth).toBe(640);
    expect(frame.processingMs).toBe(15);
  });

  it('sends a POST with a FormData body carrying the frame and timestamp', async () => {
    apiFetchMock.mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({
        face_detected: false,
        processing_ms: 1,
        extractor: {name: 'py-feat', version: '2.1.1', detector: 'Detectorv2'},
        reasons: {},
      }),
    });

    await postDebugFrame(new Blob(['x']), 99);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://test.local/debug/multimodal/frame');
    expect(options.method).toBe('POST');
    expect(options.body).toBeInstanceOf(FormData);
    const form = options.body as FormData;
    expect(form.get('frame_timestamp_ms')).toBe('99');
    expect(form.get('frame')).toBeInstanceOf(Blob);
  });

  it('throws on an unexpected non-ok, non-503 response', async () => {
    apiFetchMock.mockResolvedValue({
      status: 500,
      ok: false,
      json: async () => ({detail: 'boom'}),
    });

    await expect(postDebugFrame(new Blob(['x']), 1)).rejects.toThrow('boom');
  });
});
