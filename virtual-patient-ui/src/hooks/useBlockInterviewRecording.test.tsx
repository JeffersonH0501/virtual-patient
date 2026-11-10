import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import type {LocalInterviewBlock} from '../recording/InterviewBlockStore';
import {useInterviewRecording as useBlockInterviewRecording} from './useInterviewRecording';
import {StrictMode, type PropsWithChildren} from 'react';

const flow = vi.hoisted(() => ({rows: new Map<string, LocalInterviewBlock>(), upload: vi.fn(), request: vi.fn(), create: vi.fn()}));
vi.mock('../services/recordings/blocks', () => ({
  blockScope: (id: number) => `account:${id}`, forgetBlockQueue: vi.fn(),
  subscribeBlockConnection: () => () => undefined,
  blockJson: (...args: unknown[]) => flow.request(...args), getBlockManifest: async () => ({blocks: []}),
  blockUploadQueue: () => ({enqueue: flow.upload, drain: async () => undefined}),
}));
vi.mock('../recording/InterviewBlockStore', () => ({InterviewBlockStore: class {
  constructor(readonly scope: string) {}
  async purgeExpired() {
    return;
  }
  async create(block: LocalInterviewBlock) {
    await flow.create();
    flow.rows.set(block.id, structuredClone(block));
  }
  async list() {
    return [...flow.rows.values()].filter((item) => item.scope === this.scope).map((item) => structuredClone(item));
  }
  async patch(id: string, patch: Partial<LocalInterviewBlock>) {
    const current = flow.rows.get(id)!;
    const next = {...current, ...patch, metadata: {...current.metadata, ...patch.metadata}};
    flow.rows.set(id, next);
    return structuredClone(next);
  }
  async append(block: LocalInterviewBlock, data: Blob, end: number) {
    if (data.size) Object.assign(block, await this.patch(block.id, {chunks: block.chunks + 1, confirmedEndMs: end}));
  }
  async discardUnsent(block: LocalInterviewBlock) {
    const current = flow.rows.get(block.id);
    if (!current || current.state !== 'capturing' || current.pendingContent || current.metadata.student_message_id || current.metadata.patient_message_id) {
      throw new Error('Only an unsent intervention can be discarded');
    }
    flow.rows.delete(block.id);
  }
}}));

const Recorder = Object.assign(vi.fn(function () {
  const target = Object.assign(new EventTarget(), {state: 'inactive'});
  return Object.assign(target, {
    start: () => {
      target.state = 'recording'; target.dispatchEvent(new Event('start'));
    },
    pause: () => {
      target.state = 'paused';
    }, resume: () => {
      target.state = 'recording';
    },
    stop: () => {
      target.state = 'inactive';
      target.dispatchEvent(Object.assign(new Event('dataavailable'), {data: new Blob(['original'])}));
      target.dispatchEvent(new Event('stop'));
    },
  });
}), {isTypeSupported: () => true});

const options = () => ({interviewId: 1, enabled: true, cameraStream: {getVideoTracks: () => [{kind: 'video', getSettings: () => ({width: 640, height: 480})}]} as unknown as MediaStream,
  microphoneStream: {getAudioTracks: () => [{kind: 'audio'}]} as unknown as MediaStream, microphoneState: 'ready' as const,
  cameraEnabled: true, microphoneEnabled: true, patientAudioEnabled: true, patientAvatar: '', patientName: 'Synthetic'});

beforeEach(() => {
  flow.rows.clear(); flow.upload.mockReset(); flow.request.mockReset(); flow.create.mockReset();
  flow.upload.mockImplementation(() => new Promise(() => undefined));
  flow.request.mockResolvedValue({segment_id: 'capture', offset_ms: 0, retention_expires_at: '2027-01-01T00:00:00Z'});
  vi.stubGlobal('MediaRecorder', Recorder);
  vi.stubGlobal('MediaStream', vi.fn(function () {
    return {};
  }));
});

it('retries local startup with the same server capture grant', async () => {
  flow.create.mockRejectedValueOnce(new Error('Synthetic OPFS start failure'));
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.canRetryStart).toBe(true));
  await act(async () => { window.dispatchEvent(new Event('online')); });
  expect(result.current.segmentId).toBeNull();
  expect(result.current.syncPending).toBe(true);
  expect(flow.request).toHaveBeenCalledTimes(1);
  await act(async () => { await result.current.retryStart(); });
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  expect(flow.request).toHaveBeenCalledTimes(1);
  unmount();
});

it('starts capture when React replays effects in Strict Mode', async () => {
  flow.request.mockImplementation((_id, _path, init: RequestInit) => new Promise((resolve, reject) => {
    init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), {once: true});
    setTimeout(() => resolve({segment_id: 'capture', offset_ms: 0, retention_expires_at: '2027-01-01T00:00:00Z'}), 0);
  }));
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()), {
    wrapper: ({children}: PropsWithChildren) => <StrictMode>{children}</StrictMode>,
  });
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  unmount();
});

it('requires recalibration after the viewport changes and online cannot clear it', async () => {
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  vi.stubGlobal('innerWidth', innerWidth + 1);
  act(() => window.dispatchEvent(new Event('resize')));
  await waitFor(() => expect(result.current.segmentId).toBeNull());
  expect(result.current.errorCode).toBe('capture-geometry-changed');
  await act(async () => { window.dispatchEvent(new Event('online')); });
  expect(result.current.syncPending).toBe(true);
  unmount();
});

it('preserves the local original and requires recovery when the page is hidden', async () => {
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  expect(result.current.errorCode).toBe('capture-interrupted');
  expect(result.current.isCapturing).toBe(false);
  expect(flow.rows.size).toBe(1);
  unmount();
});

it('pauses immediately when a capture track ends', async () => {
  const camera = Object.assign(new EventTarget(), {kind: 'video', id: 'camera-one', getSettings: () => ({width: 640, height: 480})});
  const captureOptions = {...options(), cameraStream: {getVideoTracks: () => [camera]} as unknown as MediaStream};
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(captureOptions));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  act(() => camera.dispatchEvent(new Event('ended')));
  expect(result.current.segmentId).toBeNull();
  expect(result.current.errorCode).toBe('capture-device-changed');
  unmount();
});

it('does not reuse calibration after the camera track is replaced', async () => {
  const stream = (id: string) => ({getVideoTracks: () => [{kind: 'video', id, getSettings: () => ({width: 640, height: 480})}]}) as unknown as MediaStream;
  const captureOptions = {...options(), cameraStream: stream('one')};
  const {result, rerender, unmount} = renderHook((value) => useBlockInterviewRecording(value), {initialProps: captureOptions});
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  rerender({...captureOptions, cameraStream: stream('two')});
  await waitFor(() => expect(result.current.errorCode).toBe('capture-device-changed'));
  expect(result.current.segmentId).toBeNull();
  unmount();
});

it('requires recalibration when the device changes while hypotheses are open', async () => {
  const stream = (id: string) => ({getVideoTracks: () => [{kind: 'video', id, getSettings: () => ({width: 640, height: 480})}]}) as unknown as MediaStream;
  const captureOptions = {...options(), cameraStream: stream('one')};
  const {result, rerender, unmount} = renderHook((value) => useBlockInterviewRecording(value), {initialProps: captureOptions});
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  await act(async () => { await result.current.sealForEnding(); });
  rerender({...captureOptions, cameraStream: stream('two')});
  expect(result.current.canRestartWithCurrentGeometry()).toBe(false);
  unmount();
});

it('does not discard a confirmed exchange when sealing after storage fails', async () => {
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  act(() => result.current.beginPatientTurn(10));
  await act(async () => { expect(await result.current.sealForEnding()).toBe(false); });
  expect(flow.rows.size).toBe(1);
  unmount();
});

it('flushes the final fragment before same-tab recovery without discarding the original', async () => {
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  act(() => result.current.beginPatientTurn(10));
  await act(async () => { await result.current.stopForRecovery(); });
  const block = [...flow.rows.values()][0];
  expect(block.chunks).toBe(1);
  expect(block.state).toBe('capturing');
  expect(block.metadata.patient_message_id).toBe(10);
  expect(result.current.segmentId).toBeNull();
  expect(flow.upload).not.toHaveBeenCalled();
  unmount();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals(); vi.restoreAllMocks();
});

it('starts the next intervention while the previous original is still uploading', async () => {
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  act(() => result.current.beginPatientTurn(10));
  act(() => result.current.endPatientTurn(10, true));
  await waitFor(() => expect(flow.upload).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(result.current.syncPending).toBe(false));
  expect([...flow.rows.values()].filter((item) => item.state === 'closed')).toHaveLength(1);
  expect([...flow.rows.values()].filter((item) => item.state === 'capturing')).toHaveLength(1);
  expect(result.current.routePatientAudio()).toBe(false);
  unmount();
});

it('opens hypotheses without uploading the unsent intervention and cancellation starts a fresh block', async () => {
  const {result, unmount} = renderHook(() => useBlockInterviewRecording(options()));
  await waitFor(() => expect(result.current.segmentId).toBe('capture'));
  const firstId = result.current.prepareStudentTurn().block_id;
  await act(async () => {
    expect(await result.current.sealForEnding()).toBe(true);
  });
  expect(flow.upload).not.toHaveBeenCalled();
  expect(flow.rows.has(firstId!)).toBe(false);
  await act(async () => {
    await result.current.restartAfterCancel();
  });
  await waitFor(() => expect(result.current.status).toBe('recording'));
  expect(result.current.prepareStudentTurn().block_id).not.toBe(firstId);
  unmount();
});
