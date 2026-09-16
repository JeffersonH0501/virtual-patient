import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';

// DEV/DEBUG-ONLY multimodal debug service.
//
// These endpoints return RAW, frame-level extractor observations with no
// persistence. They exist solely to inspect what the multimodal extractors see
// in real time while calibrating. They MUST NOT be used to derive processed
// features, base/integrated labels, or aggregates.

// Metadata about the visual extractor that produced a frame observation.
// The extractor is now OpenFace 3.0; the type name is kept stable as a
// wire-contract identifier mirroring the backend schema class.
export type PyFeatExtractorInfo = {
  name: string;
  version: string;
  detector: string;
};

// Raw per-frame visual observation (camelCase, produced by transformToCamelCase
// from the snake_case backend payload). Produced by the OpenFace 3.0 extractor;
// the type name is kept stable as a wire-contract identifier mirroring the
// backend schema class. Every measurable value is nullable so a missing/low-
// quality frame is represented as "not available", never as zero.
export type PyFeatFrameDebug = {
  faceDetected: boolean;
  faceScore: number | null;
  gazeYaw: number | null;
  gazePitch: number | null;
  headYaw: number | null;
  headPitch: number | null;
  headRoll: number | null;
  au12: number | null;
  // Landmarks are image-pixel [x, y] pairs relative to the (unmirrored) frame
  // that was uploaded; imageWidth/imageHeight describe that frame.
  landmarks: number[][] | null;
  imageWidth: number | null;
  imageHeight: number | null;
  frameTimestampMs: number | null;
  processingMs: number;
  extractor: PyFeatExtractorInfo;
  // Short machine reasons keyed by field/topic (e.g. face_not_detected).
  reasons: Record<string, string>;
};

// Names of the underlying OpenSMILE features backing each reported value.
export type OpenSmileFeatureNames = {
  f0: string;
  loudness: string;
  voicing: string;
};

// Raw per-chunk OpenSMILE observation (camelCase).
export type OpenSmileFrameDebug = {
  f0Semitones: number | null;
  loudness: number | null;
  voicing: number | null;
  voicingKind: string | null;
  featureNames: OpenSmileFeatureNames;
  featureSet: 'eGeMAPSv02';
  frameTimestampMs: number | null;
  processingMs: number;
  reasons: Record<string, string>;
};

// Returned (HTTP 503 body) when an extractor is not available on the backend.
export type DebugUnavailable = {
  available: false;
  reason: string;
};

// Type guard so callers can branch on availability without casting.
export const isDebugUnavailable = (
  value: PyFeatFrameDebug | OpenSmileFrameDebug | DebugUnavailable,
): value is DebugUnavailable =>
  (value as DebugUnavailable).available === false;

const parseUnavailable = async (response: Response): Promise<DebugUnavailable> => {
  const body = (await response.json().catch(() => ({}))) as Partial<DebugUnavailable>;
  return {
    available: false,
    reason: typeof body.reason === 'string' ? body.reason : 'unavailable',
  };
};

// POST a single JPEG/PNG frame for raw Py-Feat inspection. Returns the raw
// observation, or a DebugUnavailable when the extractor is offline (HTTP 503).
// Throws only on unexpected non-ok responses so transient issues surface.
export const postDebugFrame = async (
  frameBlob: Blob,
  frameTimestampMs: number,
  signal?: AbortSignal,
): Promise<PyFeatFrameDebug | DebugUnavailable> => {
  const form = new FormData();
  form.append('frame', frameBlob, 'debug-frame');
  form.append('frame_timestamp_ms', String(frameTimestampMs));
  const response = await apiFetch(`${API_URL}/debug/multimodal/frame`, {
    method: 'POST',
    // No Content-Type: let the browser set the multipart boundary.
    headers: getAuthHeaders(),
    body: form,
    signal,
  });
  if (response.status === 503) return parseUnavailable(response);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Debug frame request failed');
  }
  return transformToCamelCase(await response.json()) as PyFeatFrameDebug;
};

// POST a single self-contained audio chunk for raw OpenSMILE inspection.
export const postDebugAudio = async (
  audioBlob: Blob,
  frameTimestampMs: number,
  signal?: AbortSignal,
): Promise<OpenSmileFrameDebug | DebugUnavailable> => {
  const form = new FormData();
  form.append('audio', audioBlob, 'debug-audio');
  form.append('frame_timestamp_ms', String(frameTimestampMs));
  const response = await apiFetch(`${API_URL}/debug/multimodal/audio`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
    signal,
  });
  if (response.status === 503) return parseUnavailable(response);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Debug audio request failed');
  }
  return transformToCamelCase(await response.json()) as OpenSmileFrameDebug;
};
