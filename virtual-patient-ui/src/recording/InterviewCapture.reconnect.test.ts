import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {CaptureSyncError} from './CaptureSyncError';
import {InterviewCapture, type CaptureInputs, type CaptureState} from './InterviewCapture';
import type {LocalInterviewTurn} from './InterviewTurnStore';

type Recorder = {paused: boolean; stopped: boolean};
const flow = vi.hoisted(() => ({
  request: vi.fn(),
  manifest: vi.fn(),
  queue: {enqueue: vi.fn(), drain: vi.fn(), retryTransient: vi.fn()},
  recorders: [] as {paused: boolean; stopped: boolean}[],
}));

vi.mock('../services/recordings/turns', () => ({
  turnScope: (id: number) => `account:${id}`,
  forgetTurnQueue: vi.fn(),
  turnJson: (...args: unknown[]) => flow.request(...args),
  getTurnManifest: (...args: unknown[]) => flow.manifest(...args),
  turnUploadQueue: () => flow.queue,
}));
vi.mock('./InterviewTurnStore', () => ({
  InterviewTurnStore: vi.fn(function store(this: Record<string, unknown>, scope: string) {
    Object.assign(this, {scope, purgeExpired: async () => undefined, discardUnsent: async () => undefined,
      patch: async (_id: string, patch: Partial<LocalInterviewTurn>) => patch});
  }),
}));
vi.mock('./InterviewTurnRecorder', () => ({
  InterviewTurnRecorder: class {
    state: Recorder = {paused: false, stopped: false};
    constructor(readonly store: unknown, readonly turn: LocalInterviewTurn) {
      flow.recorders.push(this.state);
    }
    async start() {
      return;
    }
    async stop() {
      this.state.stopped = true;
    }
    elapsed() {
      return 1000;
    }
    pause() {
      this.state.paused = true;
    }
    resume() {
      this.state.paused = false;
      return true;
    }
    async checkpoint() {
      return;
    }
    async close(metadata: LocalInterviewTurn['metadata']) {
      this.state.stopped = true;
      return {...this.turn, metadata, state: 'closed'} as LocalInterviewTurn;
    }
  },
}));

const track = (kind: string) => ({id: kind, readyState: 'live', getSettings: () => ({width: 1280, height: 720})});
const inputs: CaptureInputs = {
  interviewId: 7,
  cameraStream: {getVideoTracks: () => [track('cam')]} as unknown as MediaStream,
  microphoneStream: {getAudioTracks: () => [track('mic')]} as unknown as MediaStream,
};
const segmentRequests = () => flow.request.mock.calls.filter(([, path]) => path === '/recording/segments');
const startBody = () => String(segmentRequests()[0][2].body);
const stale = () => new CaptureSyncError(409, 'stale_capture');
const closed = () => new CaptureSyncError(409, 'capture_closed');
const lost = () => new TypeError('Synthetic dropped connection');

/** A server that confirms the segment named in the request, as the idempotent start endpoint does. */
const confirmingServer = () => flow.request.mockImplementation(async (_id: number, path: string, init: RequestInit) => {
  if (path === '/recording/segments') {
    return {segment_id: JSON.parse(String(init.body)).request_id, retention_expires_at: new Date(Date.now() + 86_400_000).toISOString(), offset_ms: 0};
  }
  return {duration_ms: 1000, recording_status: 'ready'};
});

const armed = async () => {
  const changes: CaptureState[] = [];
  const capture = new InterviewCapture(() => inputs, (state) => changes.push(state));
  await capture.arm();
  expect(capture.snapshot.status).toBe('recording');
  return {capture, recorder: () => flow.recorders[flow.recorders.length - 1]};
};

beforeEach(() => {
  vi.useFakeTimers();
  flow.request.mockReset(); flow.manifest.mockReset(); flow.recorders.length = 0;
  flow.queue.enqueue.mockReset().mockResolvedValue(undefined);
  flow.queue.drain.mockReset().mockResolvedValue(undefined);
  flow.queue.retryTransient.mockReset().mockReturnValue(0);
  flow.manifest.mockResolvedValue({turns: [{turn_media_id: 'turn-1', message_id: null, student_video_source: '/media'}]});
  confirmingServer();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('reconnection', () => {
  it('stays paused until the server confirms the same segment, and never creates another one', async () => {
    const {capture, recorder} = await armed();
    capture.goOffline();
    expect(recorder().paused).toBe(true);
    expect(capture.snapshot).toMatchObject({syncPending: true, reconnecting: true});
    await capture.goOnline();
    expect(recorder().paused).toBe(false);
    expect(capture.snapshot).toMatchObject({syncPending: false, reconnecting: false, errorCode: null});
    const [start, probe] = segmentRequests();
    expect(segmentRequests()).toHaveLength(2);
    // The probe replays the original request: same request ID, same content, so the server can only answer, not create.
    expect(probe[2].body).toBe(start[2].body);
    expect(flow.request.mock.calls.some(([, path]) => String(path).includes('capture/state'))).toBe(false);
  });

  it('shares one probe between the browser event, the transport report and the retry timer', async () => {
    const {capture} = await armed();
    capture.goOffline();
    await Promise.all([capture.goOnline(), capture.goOnline(), capture.goOnline()]);
    expect(segmentRequests()).toHaveLength(2);
  });

  it('keeps capture paused and retries with backoff through transient failures without invalidating it', async () => {
    const {capture, recorder} = await armed();
    flow.request.mockRejectedValueOnce(lost())
      .mockRejectedValueOnce(new CaptureSyncError(503, 'busy'))
      .mockRejectedValueOnce(new DOMException('probe timed out', 'TimeoutError'));
    capture.goOffline();
    await capture.goOnline();
    expect(capture.snapshot).toMatchObject({syncPending: true, reconnecting: true, errorCode: null});
    expect(recorder().paused).toBe(true);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(capture.snapshot.errorCode).toBeNull();
    await vi.advanceTimersByTimeAsync(2_000);
    expect(capture.snapshot.errorCode).toBeNull();
    expect(recorder().paused).toBe(true);
    await vi.advanceTimersByTimeAsync(4_000);
    expect(recorder().paused).toBe(false);
    expect(capture.snapshot).toMatchObject({syncPending: false, reconnecting: false, errorCode: null});
    expect(segmentRequests()).toHaveLength(5);
  });

  it('survives repeated microcuts and distrusts a probe answered after the link dropped again', async () => {
    const {capture, recorder} = await armed();
    let answer!: (value: unknown) => void;
    capture.goOffline();
    flow.request.mockImplementationOnce(() => new Promise((resolve) => {
      answer = resolve;
    }));
    const first = capture.goOnline();
    capture.goOffline();
    answer({segment_id: JSON.parse(startBody()).request_id});
    await first;
    // The stale answer was not enough: a second probe confirmed the second outage.
    expect(segmentRequests()).toHaveLength(3);
    expect(recorder().paused).toBe(false);
    for (let cut = 0; cut < 5; cut += 1) {
      capture.goOffline();
      expect(recorder().paused).toBe(true);
      await capture.goOnline();
      expect(recorder().paused).toBe(false);
    }
    expect(capture.snapshot).toMatchObject({syncPending: false, errorCode: null});
    expect(flow.recorders).toHaveLength(1);
  });

  it('does not restart a recorder the user paused on purpose', async () => {
    const {capture, recorder} = await armed();
    capture.pause();
    capture.goOffline();
    await capture.goOnline();
    expect(recorder().paused).toBe(true);
    expect(capture.snapshot.syncPending).toBe(false);
  });

  it('sends the originals that failed during the outage again once the capture is confirmed', async () => {
    const {capture} = await armed();
    capture.goOffline();
    await capture.goOnline();
    expect(flow.queue.retryTransient).toHaveBeenCalledOnce();
  });

  it('clears the pause after a reconnection while the capture is sealed, so the student can continue', async () => {
    const {capture} = await armed();
    await capture.seal();
    capture.goOffline();
    await capture.goOnline();
    expect(capture.snapshot.syncPending).toBe(false);
    await capture.reopen();
    expect(capture.snapshot).toMatchObject({status: 'recording', syncPending: false});
  });
});

describe('definitive server verdicts', () => {
  it.each([
    ['a replaced writer', stale(), 'capture-superseded'],
    ['an unrelated conflict', new CaptureSyncError(409, 'Segment request ID is already in use'), 'capture-superseded'],
    ['an ended recording or interview', closed(), 'capture-closed'],
    ['a deleted interview', new CaptureSyncError(404, 'Interview not found'), 'capture-closed'],
    ['an expired retention', new CaptureSyncError(410, 'Recording retention has expired'), 'capture-closed'],
  ])('does not resume after %s and does not keep probing', async (_name, error, code) => {
    const {capture, recorder} = await armed();
    capture.goOffline();
    flow.request.mockRejectedValueOnce(error);
    await capture.goOnline();
    expect(capture.snapshot).toMatchObject({errorCode: code, syncPending: true, reconnecting: false});
    expect(recorder().paused).toBe(true);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(segmentRequests()).toHaveLength(2);
  });

  it('treats an answer naming another segment as a replaced writer', async () => {
    const {capture, recorder} = await armed();
    capture.goOffline();
    flow.request.mockResolvedValueOnce({segment_id: 'another-segment'});
    await capture.goOnline();
    expect(capture.snapshot.errorCode).toBe('capture-superseded');
    expect(recorder().paused).toBe(true);
  });

  it('leaves a device or geometry block alone: a reconnection cannot recalibrate', async () => {
    const {capture, recorder} = await armed();
    capture.invalidate('capture-device-changed');
    capture.goOffline();
    await capture.goOnline();
    expect(segmentRequests()).toHaveLength(1);
    expect(capture.snapshot).toMatchObject({errorCode: 'capture-device-changed', reconnecting: false});
    expect(recorder().paused).toBe(true);
  });

  it('makes no request once the resume flow has taken over the capture', async () => {
    const {capture} = await armed();
    capture.goOffline();
    await capture.stopForRecovery();
    await capture.goOnline();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(segmentRequests()).toHaveLength(1);
    expect(capture.snapshot.errorCode).toBeNull();
  });
});

describe('recovery of the storage block', () => {
  it('stays paused while the transport is down and continues once the capture is confirmed', async () => {
    const {capture, recorder} = await armed();
    capture.goOffline();
    capture.invalidate('temporary-storage-failed');
    flow.request.mockRejectedValueOnce(lost());
    expect(await capture.attemptStorageRecovery()).toBe(true);
    expect(capture.snapshot.syncPending).toBe(true);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(recorder().paused).toBe(false);
    expect(capture.snapshot).toMatchObject({syncPending: false, errorCode: null});
  });
});

describe('page reload', () => {
  it('a reloaded page cannot reuse the old segment: the server demands the resume flow', async () => {
    const reloaded = new InterviewCapture(() => inputs, () => undefined);
    flow.request.mockRejectedValueOnce(new CaptureSyncError(409, 'An existing capture must be resumed'));
    await reloaded.arm();
    expect(reloaded.snapshot).toMatchObject({status: 'failed', errorCode: 'capture-start-failed'});
    expect(flow.recorders).toHaveLength(0);
    await reloaded.goOnline();
    expect(segmentRequests()).toHaveLength(1);
  });
});

describe('finalization after a recovery', () => {
  it('finalizes once with the confirmed originals', async () => {
    const {capture} = await armed();
    capture.goOffline();
    flow.request.mockRejectedValueOnce(lost());
    await capture.goOnline();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(capture.snapshot.syncPending).toBe(false);
    expect(await capture.finalize()).toBe(true);
    const finalizations = flow.request.mock.calls.filter(([, path]) => path === '/recording/turns/finalize');
    expect(finalizations).toHaveLength(1);
    expect(JSON.parse(finalizations[0][2].body)).toMatchObject({turn_media_ids: ['turn-1']});
    expect(finalizations[0][2].headers['X-Capture-Segment']).toBe(JSON.parse(startBody()).request_id);
  });

  it('retries originals that failed for a transient reason before declaring them missing', async () => {
    const {capture} = await armed();
    flow.queue.retryTransient.mockReturnValueOnce(1).mockReturnValue(0);
    expect(await capture.finalize()).toBe(true);
    expect(flow.queue.drain).toHaveBeenCalledTimes(2);
  });

  it('stops retrying a failing original after a bounded number of rounds', async () => {
    const {capture} = await armed();
    flow.queue.retryTransient.mockReturnValue(1);
    expect(await capture.finalize()).toBe(true);
    expect(flow.queue.drain).toHaveBeenCalledTimes(3);
  });

  it('does not report the recording it just closed as an ended capture when the link drops during completion', async () => {
    const {capture} = await armed();
    expect(await capture.finalize()).toBe(true);
    capture.goOffline();
    // After finalization the server answers capture_closed to a replay; that is the expected state, not a failure.
    flow.request.mockRejectedValue(closed());
    await capture.goOnline();
    expect(capture.snapshot).toMatchObject({errorCode: null, syncPending: false, reconnecting: false});
    expect(segmentRequests()).toHaveLength(1);
  });

  it('reports a request that never answers as a timeout the student can retry', async () => {
    const {capture} = await armed();
    flow.manifest.mockRejectedValueOnce(new DOMException('no answer', 'TimeoutError'));
    expect(await capture.finalize()).toBe(false);
    expect(capture.snapshot.errorCode).toBe('finalize-timeout');
    expect(await capture.finalize()).toBe(true);
  });

  it('does not block finalization on an upload that never settles', async () => {
    const {capture} = await armed();
    flow.queue.drain.mockReturnValue(new Promise(() => undefined));
    const finalizing = capture.finalize();
    await vi.advanceTimersByTimeAsync(180_000);
    expect(await finalizing).toBe(false);
    expect(capture.snapshot.errorCode).toBe('finalize-timeout');
  });
});
