import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {useLayoutEffect} from 'react';
import {useTechnicalCalibration} from './useTechnicalCalibration';

vi.mock('../utils/mediaRecorder', () => ({selectVideoMimeType: () => 'video/webm'}));
class Recorder {
  static instances: Recorder[] = [];
  state = 'inactive';
  ondataavailable?: (event: {data: Blob}) => void;
  onstop?: () => void;
  onerror?: () => void;
  onstart?: () => void;
  constructor() { Recorder.instances.push(this); }
  start() { this.state = 'recording'; this.onstart?.(); }
  pause() {
    this.state = 'paused';
  }
  resume() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({data: new Blob(['synthetic'])});
    this.onstop?.();
  }
}
const track = {clone: () => ({stop: vi.fn()}), getSettings: () => ({width: 1280, height: 720})};
const stream = {active: true, getAudioTracks: () => [track], getVideoTracks: () => [track]} as unknown as MediaStream;
const useCapture = () => {
  const capture = useTechnicalCalibration(stream, stream);
  useLayoutEffect(() => {
    if (capture.phase === 'gaze_targets') capture.confirmPresentation(capture.activeTarget?.order ?? null);
    if (capture.phase === 'camera_reference') capture.confirmPresentation(null);
    if (capture.phase === 'guided_check' && capture.activeCheck) capture.confirmPresentation(capture.activeCheck);
  }, [capture.phase, capture.activeTarget, capture.activeCheck, capture.confirmPresentation]);
  return capture;
};
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); Recorder.instances = []; });
it('records five targets and the camera reference continuously in one file', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', class { constructor(private tracks: unknown[]) {} getTracks() { return this.tracks; } });
  vi.stubGlobal('AudioContext', undefined);
  const {result} = renderHook(useCapture);
  let started!: Promise<void>;
  act(() => { started = result.current.start('unified'); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); await started; });
  expect(result.current.phase).toBe('gaze_targets');
  for (let i = 0; i < 5; i++) await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
  expect(result.current.phase).toBe('camera_reference');
  expect(result.current.activeTarget).toBeNull();
  expect(Recorder.instances).toHaveLength(1);
  expect(Recorder.instances[0].state).toBe('recording');
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(result.current.phase).toBe('complete');
  expect(result.current.media?.stage).toBe('unified');
  expect(result.current.media?.metadata).toMatchObject({gazeSource:'mediapipe_five_point_v1',cameraReferenceStartMs: 20_250, cameraReferenceEndMs: 25_000, geometryStable: true});
  expect(result.current.media?.metadata.targets).toHaveLength(5);
});

it('finishes normal calibration before starting a separate guided recording', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', class { constructor(private tracks: unknown[]) {} getTracks() { return this.tracks; } });
  vi.stubGlobal('AudioContext', undefined);
  const {result} = renderHook(useCapture);
  let started!: Promise<void>;
  act(() => { started = result.current.start('unified', {guidedChecksEnabled: true}); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); await started; });
  for (let i = 0; i < 5; i++) await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(result.current.phase).toBe('complete');
  expect(result.current.media?.metadata.cameraReferenceEndMs).toBe(25000);
  expect(result.current.media?.metadata.guidedChecks).toBeUndefined();
  await act(async () => { await result.current.start('guided', {attestations: {gaze: 'signed-gaze', camera: 'signed-camera'}}); });
  const phases = ['gaze_still', 'gaze_turn', 'gaze_nod', 'gaze_away', 'gaze_camera', 'nod_still', 'nod_three', 'head_shake', 'smile_neutral', 'smile_speech', 'smile_silent', 'smile_speech_positive'];
  for (const [index, duration] of [5000,6000,6000,5000,5000,5000,10000,8000,5000,8000,5000,8000].entries()) {
    expect(result.current.phase).toBe('guided_check');
    expect(result.current.activeCheck).toBe(phases[index]);
    expect(result.current.media).toBeNull();
    expect(result.current.waitingForStep).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    act(() => result.current.startGuidedStep());
    await act(async () => { await vi.advanceTimersByTimeAsync(duration); });
  }
  expect(result.current.phase).toBe('complete');
  expect(result.current.media?.metadata.cameraReferenceEndMs).toBeUndefined();
  expect(result.current.media?.metadata.guidedChecks).toHaveLength(12);
  expect(result.current.media?.metadata.attestations).toEqual({gaze: 'signed-gaze', camera: 'signed-camera'});
  expect(result.current.media?.durationMs).toBe(76000);
  expect(Recorder.instances).toHaveLength(2);
});


it('starts the nonverbal-only test with nods rather than gaze prompts', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', class { constructor(private tracks: unknown[]) {} getTracks() { return this.tracks; } });
  vi.stubGlobal('AudioContext', undefined);
  const {result} = renderHook(useCapture);
  await act(async () => { await result.current.start('guided', {nonverbalOnly: true, attestations: {}}); });
  expect(result.current.activeCheck).toBe('nod_still');
  expect(result.current.waitingForStep).toBe(true);
});

it('does not publish media after a recorder error and late stop event', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', class { constructor(private tracks: unknown[]) {} getTracks() { return this.tracks; } });
  vi.stubGlobal('AudioContext', undefined);
  const {result} = renderHook(useCapture);
  let started!: Promise<void>;
  act(() => { started = result.current.start('unified'); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); await started; });
  const recorder = Recorder.instances[0];
  const lateStop = recorder.onstop;
  act(() => { recorder.onerror?.(); recorder.ondataavailable?.({data: new Blob(['bad'])}); lateStop?.(); });
  expect(result.current.phase).toBe('error');
  expect(result.current.media).toBeNull();
  expect(vi.getTimerCount()).toBe(0);
});


it('records actual target commits instead of advancing through unseen targets', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', class { constructor(private tracks: unknown[]) {} getTracks() { return this.tracks; } });
  vi.stubGlobal('AudioContext', undefined);
  const {result} = renderHook(() => useTechnicalCalibration(stream, stream));
  let started!: Promise<void>;
  act(() => { started = result.current.start('unified'); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); await started; });
  act(() => result.current.confirmPresentation(1));
  await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
  expect(result.current.activeTarget?.order).toBe(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  expect(result.current.activeTarget?.order).toBe(2);
  act(() => result.current.confirmPresentation(2));
  for (let order = 3; order <= 5; order++) {
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    act(() => result.current.confirmPresentation(order));
  }
  await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
  act(() => result.current.confirmPresentation(null));
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  const targets = result.current.media?.metadata.targets as Array<{presentationStartMs: number; presentationEndMs: number}>;
  expect(targets[0].presentationEndMs).toBe(4800);
  expect(targets[1].presentationStartMs).toBe(4800);
  expect(result.current.media?.durationMs).toBe(25800);
});

it('cancels countdown without starting a late recorder', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('AudioContext', undefined);
  const {result} = renderHook(useCapture);
  let started!: Promise<void>;
  act(() => { started = result.current.start('unified'); });
  act(() => result.current.cancel());
  await act(async () => { await vi.advanceTimersByTimeAsync(6000); await started; });
  expect(result.current.phase).toBe('error');
  expect(Recorder.instances).toHaveLength(0);
  expect(vi.getTimerCount()).toBe(0);
});


it('rejects a renderer stall longer than the observation settling margin', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', class { constructor(private tracks: unknown[]) {} getTracks() { return this.tracks; } });
  vi.stubGlobal('AudioContext', undefined);
  let frame!: FrameRequestCallback;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frame = callback; return 1; });
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const {result} = renderHook(useCapture);
  let started!: Promise<void>;
  act(() => { started = result.current.start('unified'); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); await started; });
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
  act(() => frame(performance.now()));
  expect(result.current.failureReason).toBe('timing_unstable');
  expect(result.current.media).toBeNull();
  expect(result.current.phase).toBe('error');
});
