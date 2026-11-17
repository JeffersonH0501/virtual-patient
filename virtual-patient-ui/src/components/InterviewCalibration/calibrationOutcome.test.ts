import {expect, it} from 'vitest';
import {interpretCalibrationFailure, interpretCalibrationResult} from './calibrationOutcome';

const gaze = {stage: 'gaze' as const, status: 'passed' as const, failureReason: null, result: {quality: {a: 1}}, attestation: 'g'};

it('keeps the gaze checkpoint and repeats only the camera when the unified camera reference fails', () => {
  const camera = {stage: 'camera' as const, status: 'failed' as const, failureReason: 'camera_unstable', result: null};
  const outcome = interpretCalibrationResult('unified', {stage: 'unified', status: 'failed', failureReason: 'camera_unstable',
    result: {checkpoints: {gaze, camera}, failedStage: 'camera'}}, false);
  expect(outcome).toMatchObject({reset: true, passed: {gaze}, display: camera, nextStage: 'camera'});
});

it('restarts the whole sequence after a geometry failure', () => {
  const outcome = interpretCalibrationResult('camera', {stage: 'camera', status: 'failed', failureReason: 'geometry', result: null}, false);
  expect(outcome).toMatchObject({reset: true, passed: {}, nextStage: 'unified'});
});

it('classifies upload failures so the same video can be resent', () => {
  expect(interpretCalibrationFailure('unified', new TypeError('network')).display.failureReason).toBe('upload_failed');
  expect(interpretCalibrationFailure('unified', Object.assign(new Error('large'), {status: 413})).display.failureReason).toBe('upload_too_large');
  expect(interpretCalibrationFailure('unified', Object.assign(new Error('gone'), {status: 410}))).toMatchObject({draftExpired: true, reset: true});
  expect(interpretCalibrationFailure('unified', new Error('boom')).display.failureReason).toBe('processing_failed');
});
