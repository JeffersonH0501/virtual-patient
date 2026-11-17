import type {CalibrationStage, CalibrationStageResult, GuidedCheckDiagnostics} from '../../services/interviews/calibration';

export type Checkpoint = 'gaze' | 'camera';
export type CheckpointResults = Partial<Record<Checkpoint, CalibrationStageResult>>;

/** How the screen should react to one processed capture. */
export type CalibrationOutcome = {
  display: CalibrationStageResult;
  diagnostics?: GuidedCheckDiagnostics | null;
  /** Checkpoints accepted by this response; `reset` discards earlier ones first. */
  passed: CheckpointResults;
  reset: boolean;
  /** Capture to repeat next; undefined keeps the current one. */
  nextStage?: CalibrationStage;
  draftExpired?: boolean;
};

const statusOf = (failure: unknown) => failure instanceof Error && 'status' in failure ? Number(failure.status) : null;
const failed = (stage: CalibrationStage, failureReason: string): CalibrationStageResult =>
  ({stage, status: 'failed', failureReason, result: null});

export const interpretCalibrationResult = (stage: CalibrationStage, result: CalibrationStageResult,
  calibrationTest: boolean): CalibrationOutcome => {
  const diagnostics = (result.result?.guidedChecks as GuidedCheckDiagnostics | undefined) ?? null;
  if (stage === 'guided') return {display: result, diagnostics, passed: {}, reset: false};
  if (stage === 'unified') {
    // One video yields both checkpoints; a camera-only failure keeps the gaze checkpoint.
    const checkpoints = result.result?.checkpoints as CheckpointResults | undefined;
    const passed: CheckpointResults = {};
    for (const checkpoint of ['gaze', 'camera'] as const) {
      if (checkpoints?.[checkpoint]?.status === 'passed') passed[checkpoint] = checkpoints[checkpoint];
    }
    const failedStage = result.result?.failedStage as Checkpoint | undefined;
    const display = checkpoints?.[failedStage ?? 'camera'] ?? {...result, stage: 'gaze'};
    const gazeQuality = checkpoints?.gaze?.result?.quality as Record<string, unknown> | undefined;
    return {
      diagnostics, passed, reset: true,
      display: calibrationTest && gazeQuality ? {...display, result: {...display.result,
        quality: {...(display.result?.quality as Record<string, unknown> ?? {}), ...gazeQuality},
        experimentalQualityBypass: result.result?.experimentalQualityBypass ?? display.result?.experimentalQualityBypass}} : display,
      nextStage: failedStage === 'camera' && result.failureReason !== 'geometry' ? 'camera' : 'unified',
    };
  }
  if (result.failureReason === 'geometry') return {display: result, passed: {}, reset: true, nextStage: 'unified'};
  return {display: result, passed: result.status === 'passed' ? {[result.stage as Checkpoint]: result} : {}, reset: false};
};

export const interpretCalibrationFailure = (stage: CalibrationStage, failure: unknown): CalibrationOutcome => {
  const status = statusOf(failure);
  if (status === 404 || status === 410) {
    return {display: failed('gaze', 'draft_expired'), passed: {}, reset: true, nextStage: 'unified', draftExpired: true};
  }
  if (stage === 'guided' && status === 422) return {display: failed('gaze', 'geometry'), passed: {}, reset: true, nextStage: 'unified'};
  const network = failure instanceof TypeError || (failure instanceof DOMException && failure.name === 'TimeoutError') ||
    status === 409 || status === 503;
  return {display: failed(stage, status === 413 ? 'upload_too_large' : network ? 'upload_failed' : 'processing_failed'),
    passed: {}, reset: false};
};
