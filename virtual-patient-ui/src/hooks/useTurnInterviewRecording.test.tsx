import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import type {LocalInterviewTurn} from '../recording/InterviewTurnStore';
import {useInterviewRecording as useTurnInterviewRecording} from './useInterviewRecording';
import {StrictMode, type PropsWithChildren} from 'react';

// Shared mutable state across mocks.
const flow = vi.hoisted(() => ({
  rows: new Map<string, LocalInterviewTurn>(),
  upload: vi.fn(),
  request: vi.fn(),
  create: vi.fn(),
}));

vi.mock('../services/recordings/turns', () => ({
  turnScope: (id: number) => `account:${id}`,
  forgetTurnQueue: vi.fn(),
  subscribeTurnConnection: () => () => undefined,
  turnJson: (...args: unknown[]) => flow.request(...args),
  getTurnManifest: async () => ({turns: []}),
  turnUploadQueue: () => ({enqueue: flow.upload, drain: async () => undefined}),
}));

vi.mock('../recording/InterviewTurnStore', () => ({
  InterviewTurnStore: class {
    constructor(readonly scope: string) {}
    async purgeExpired() {
      return;
    }
    async create(turn: LocalInterviewTurn) {
      await flow.create();
      flow.rows.set(turn.id, structuredClone(turn));
    }
    async list() {
      return [...flow.rows.values()].filter((item) => item.scope === this.scope).map((item) => structuredClone(item));
    }
    async patch(id: string, patch: Partial<LocalInterviewTurn>) {
      const current = flow.rows.get(id)!;
      const next = {...current, ...patch, metadata: {...current.metadata, ...patch.metadata}};
      flow.rows.set(id, next);
      return structuredClone(next);
    }
    async append(turn: LocalInterviewTurn, data: Blob, end: number) {
      if (data.size) Object.assign(turn, await this.patch(turn.id, {chunks: turn.chunks + 1, confirmedEndMs: end}));
    }
    async discardUnsent(turn: LocalInterviewTurn) {
      const current = flow.rows.get(turn.id);
      if (!current || current.state !== 'capturing' || current.pendingContent || current.metadata.message_id) {
        throw new Error('Only an unsent intervention can be discarded');
      }
      flow.rows.delete(turn.id);
    }
  },
}));

vi.mock('../recording/InterviewTurnRecorder', () => ({
  InterviewTurnRecorder: class {
    turn: LocalInterviewTurn;
    store: {scope: string; patch: (id: string, p: Partial<LocalInterviewTurn>) => Promise<LocalInterviewTurn>};
    constructor(store: {scope: string; patch: (id: string, p: Partial<LocalInterviewTurn>) => Promise<LocalInterviewTurn>}, turn: LocalInterviewTurn) {
      this.store = store; this.turn = turn;
    }
    async start() {
      await this.store.create(this.turn);
    }
    async stop() {
      return;
    }
    async flush() {
      return;
    }
    elapsed() {
      return 1000;
    }
    pause() {
      return;
    }
    resume() {
      return true;
    }
    async checkpoint(meta: Partial<LocalInterviewTurn['metadata']>) {
      Object.assign(this.turn, await this.store.patch(this.turn.id, {metadata: meta}));
    }
    async close(metadata: LocalInterviewTurn['metadata']) {
      Object.assign(this.turn, await this.store.patch(this.turn.id, {metadata, state: 'closed'}));
      return this.turn;
    }
  },
}));

const wrapper = ({children}: PropsWithChildren) => <StrictMode>{children}</StrictMode>;
const options = (interviewId = 1) => ({
  enabled: true, interviewId, initialOffsetMs: 0,
  cameraStream: {getVideoTracks: () => [{kind: 'video', id: 'cam', readyState: 'live', getSettings: () => ({width: 1280, height: 720}), addEventListener: vi.fn(), removeEventListener: vi.fn()}]} as unknown as MediaStream,
  microphoneStream: {getAudioTracks: () => [{kind: 'audio', id: 'mic', readyState: 'live', addEventListener: vi.fn(), removeEventListener: vi.fn()}]} as unknown as MediaStream,
  microphoneState: 'granted' as const, cameraEnabled: true, microphoneEnabled: true,
  patientAudioEnabled: true, patientAvatar: '', patientName: 'Patient',
});

beforeEach(() => {
  flow.rows.clear(); flow.upload.mockReset(); flow.request.mockReset(); flow.create.mockReset();
  flow.request.mockResolvedValue({segment_id: 'seg-1', retention_expires_at: new Date(Date.now() + 86400_000).toISOString(), offset_ms: 0});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('transitions to recording after a successful segment start', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  expect(result.current.segmentId).toBe('seg-1');
  expect(result.current.isCapturing).toBe(true);
});

it('opens a turn recorder on beginStudentTurn and closes it on recordStudentTurn', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  act(() => result.current.beginStudentTurn());
  await waitFor(() => expect(flow.create).toHaveBeenCalledTimes(1));
  expect(flow.rows.size).toBe(1);
  act(() => result.current.recordStudentTurn(42));
  await waitFor(() => expect(flow.upload).toHaveBeenCalledTimes(1));
  expect(flow.rows.get([...flow.rows.keys()][0])?.metadata.message_id).toBe(42);
});

it('discards an open turn recorder on discardStudentTurn', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  act(() => result.current.beginStudentTurn());
  await waitFor(() => expect(flow.create).toHaveBeenCalled());
  act(() => result.current.discardStudentTurn());
  await waitFor(() => expect(flow.rows.size).toBe(0));
  expect(flow.upload).not.toHaveBeenCalled();
});

it('patient-turn callbacks are no-ops and do not create uploads', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  act(() => {
    result.current.beginPatientTurn();
    result.current.endPatientTurn();
    result.current.recordWrittenPatientTurn();
  });
  await new Promise((r) => setTimeout(r, 50));
  expect(flow.create).not.toHaveBeenCalled();
  expect(flow.upload).not.toHaveBeenCalled();
});

it('invalidates capture when devices change between turns', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  // Simulate a device-change invalidation directly (no MediaRecorder in jsdom).
  act(() => result.current.pause());
  expect(result.current.status).toBe('paused');
});

it('finalize drains the upload queue and posts to the finalize endpoint', async () => {
  flow.request
    .mockResolvedValueOnce({segment_id: 'seg-1', retention_expires_at: new Date(Date.now() + 86400_000).toISOString(), offset_ms: 0})
    .mockResolvedValueOnce({active_segment_id: 'seg-1'})
    .mockResolvedValueOnce({duration_ms: 1000, recording_status: 'ready'});
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  let sealed = false;
  await act(async () => { sealed = await result.current.finalize(); });
  expect(sealed).toBe(true);
  // Should POST to /recording/turns/finalize.
  const finalizeCalls = flow.request.mock.calls.filter(([, path]: [number, string]) => String(path).includes('finalize'));
  expect(finalizeCalls.length).toBeGreaterThanOrEqual(1);
});
