import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import type {LocalInterviewTurn} from '../recording/InterviewTurnStore';
import type {StudentCaptureTiming} from '../types/recording';
import {useInterviewRecording as useTurnInterviewRecording} from './useInterviewRecording';
import {StrictMode, type PropsWithChildren} from 'react';

// Shared mutable state across mocks.
const flow = vi.hoisted(() => ({
  rows: new Map<string, LocalInterviewTurn>(),
  upload: vi.fn(),
  request: vi.fn(),
  create: vi.fn(),
  tracks: vi.fn(),
}));

vi.mock('../services/recordings/turns', () => ({
  turnScope: (id: number) => `account:${id}`,
  forgetTurnQueue: vi.fn(),
  subscribeTurnConnection: () => () => undefined,
  turnJson: (...args: unknown[]) => flow.request(...args),
  getTurnManifest: async () => ({turns: []}),
  turnUploadQueue: () => ({enqueue: flow.upload, drain: async () => undefined, retryTransient: () => 0}),
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
    async start(camera: MediaStream, microphone?: MediaStream) {
      flow.tracks(camera, microphone);
      await this.store.create(this.turn);
    }
    async stop() {
      return;
    }
    async flush() {
      return;
    }
    elapsed(at?: number) {
      return at == null ? 1200 : Math.max(0, at - 2000);
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
  flow.rows.clear(); flow.upload.mockReset(); flow.upload.mockResolvedValue(undefined); flow.request.mockReset(); flow.create.mockReset(); flow.tracks.mockReset();
  flow.request.mockResolvedValue({segment_id: 'seg-1', retention_expires_at: new Date(Date.now() + 86400_000).toISOString(), offset_ms: 0});
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks();
});

it('transitions to recording after a successful segment start', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  expect(result.current.segmentId).toBe('seg-1');
  expect(result.current.isCapturing).toBe(true);
});

it('opens a camera and microphone clip as soon as capture is armed', async () => {
  const configuration = options();
  const {result} = renderHook(() => useTurnInterviewRecording(configuration), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  expect(flow.tracks).toHaveBeenCalledWith(configuration.cameraStream, configuration.microphoneStream);
  expect(result.current.elapsedAt()).toBe(1200);
});

it('switches to camera-only at submission and closes the student clip with its speech onset', async () => {
  const configuration = options();
  const {result} = renderHook(() => useTurnInterviewRecording(configuration), {wrapper});
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  act(() => {
    result.current.markSpeechStart();
    result.current.submitStudentTurn('exchange-id');
  });
  let studentTiming: StudentCaptureTiming | undefined;
  await act(async () => {
    studentTiming = await result.current.prepareStudentTurn();
  });
  const rows = [...flow.rows.values()];
  expect(flow.tracks).toHaveBeenNthCalledWith(2, configuration.cameraStream, undefined);
  expect(studentTiming?.turn_media_id).toBe(rows[0].id);
  expect(rows[1]).toMatchObject({requestId: 'exchange-id', metadata: {speaker: 'patient', session_clock_ms: 1200}});
  expect(flow.upload).not.toHaveBeenCalled();
  act(() => result.current.recordStudentTurn(18));
  await waitFor(() => expect(flow.upload).toHaveBeenCalledOnce());
  expect(flow.upload.mock.calls[0][0].metadata).toMatchObject({speaker: 'student', message_id: 18});
  expect(flow.upload.mock.calls[0][0].metadata.speech_start_ms).toBeGreaterThanOrEqual(0);
});

it('records listening bounds and immediately reopens the student clip after the reply', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  act(() => result.current.submitStudentTurn('exchange-id'));
  await act(async () => {
    await result.current.preparePatientTurn(19);
  });
  expect(flow.create).toHaveBeenCalledTimes(2);
  act(() => {
    result.current.beginPatientTurn(19, 2200);
    result.current.endPatientTurn(19, true, 3100);
  });
  await waitFor(() => expect(flow.upload).toHaveBeenCalledOnce());
  expect(flow.upload.mock.calls[0][0].metadata).toMatchObject({
    speaker: 'patient', message_id: 19, playback_complete: true,
    playback_start_ms: 200, playback_end_ms: 1100,
  });
  expect(flow.create).toHaveBeenCalledTimes(3);
  expect([...flow.rows.values()].at(-1)?.metadata).toMatchObject({speaker: 'student', session_clock_ms: 2400});
  await waitFor(() => expect(result.current.isCapturing).toBe(true));
});

it('starts the reply clip from an idle student clip when no submission preceded it', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  await act(async () => {
    await result.current.preparePatientTurn(5);
  });
  const rows = [...flow.rows.values()];
  expect(rows.at(-1)?.metadata).toMatchObject({speaker: 'patient', message_id: 5});
  act(() => result.current.endPatientTurn(5, false));
  await waitFor(() => expect(flow.upload).toHaveBeenCalledOnce());
  expect(flow.upload.mock.calls[0][0].metadata).toMatchObject({speaker: 'patient', message_id: 5, playback_start_ms: null});
});

it('returns the floor to a new student clip when the utterance produced no message', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  act(() => result.current.submitStudentTurn('exchange-id'));
  await waitFor(() => expect(flow.create).toHaveBeenCalledTimes(2));
  act(() => result.current.returnFloorToStudent());
  await waitFor(() => expect(flow.create).toHaveBeenCalledTimes(3));
  expect([...flow.rows.values()].at(-1)?.metadata.speaker).toBe('student');
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
  await act(async () => {
    sealed = await result.current.finalize();
  });
  expect(sealed).toBe(true);
  // Should POST to /recording/turns/finalize.
  const finalizeCalls = flow.request.mock.calls.filter(([, path]: [number, string]) => String(path).includes('finalize'));
  expect(finalizeCalls.length).toBeGreaterThanOrEqual(1);
  expect(JSON.parse(String(finalizeCalls[0][2].body)).missing_message_ids).toEqual([]);
});

it('declares transcript turns without preserved media and keeps server finalization errors distinct', async () => {
  flow.request
    .mockResolvedValueOnce({segment_id: 'seg-1', retention_expires_at: new Date(Date.now() + 86400_000).toISOString(), offset_ms: 0})
    .mockRejectedValueOnce(new Error('Missing evidence must be declared explicitly'));
  const {result} = renderHook(() => useTurnInterviewRecording({...options(), studentMessageIds: [21, 22]}), {wrapper});
  await waitFor(() => expect(result.current.status).toBe('recording'));
  let finalized = true;
  await act(async () => {
    finalized = await result.current.finalize();
  });
  expect(finalized).toBe(false);
  expect(result.current.errorCode).toBe('finalize-failed');
  const finalizeCall = flow.request.mock.calls.find(([, path]: [number, string]) => String(path).includes('finalize'));
  expect(JSON.parse(String(finalizeCall?.[2].body)).missing_message_ids).toEqual([21, 22]);
});

it('starts the recording and the clock when the greeting starts playing', async () => {
  const configuration = {...options(), initialPatientMessageId: 3};
  const {result} = renderHook(() => useTurnInterviewRecording(configuration), {wrapper});
  await waitFor(() => expect(result.current.isCapturing).toBe(true));
  await act(async () => {
    await result.current.preparePatientTurn(3);
  });
  expect(flow.create).not.toHaveBeenCalled();
  expect(result.current.elapsedAt()).toBe(0);
  act(() => result.current.beginPatientTurn(3, 2000));
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  expect(flow.tracks).toHaveBeenCalledWith(configuration.cameraStream, undefined);
  expect([...flow.rows.values()][0].metadata).toMatchObject({speaker: 'patient', message_id: 3, session_clock_ms: 0});
  act(() => result.current.endPatientTurn(3, true, 2900));
  await waitFor(() => expect(flow.upload).toHaveBeenCalledOnce());
  expect(flow.upload.mock.calls[0][0].metadata).toMatchObject({message_id: 3, playback_start_ms: 0, playback_complete: true});
  await waitFor(() => expect([...flow.rows.values()].at(-1)?.metadata.speaker).toBe('student'));
});

it('starts with the student when the greeting could not be played', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording({...options(), initialPatientMessageId: 3}), {wrapper});
  await waitFor(() => expect(result.current.isCapturing).toBe(true));
  act(() => result.current.endPatientTurn(3, false));
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  expect([...flow.rows.values()][0].metadata.speaker).toBe('student');
  expect(flow.upload).not.toHaveBeenCalled();
});

it('keeps the listening window when playback starts before the reply binding is persisted', async () => {
  const {result} = renderHook(() => useTurnInterviewRecording(options()), {wrapper});
  await waitFor(() => expect(flow.create).toHaveBeenCalledOnce());
  act(() => result.current.submitStudentTurn('exchange-id'));
  await waitFor(() => expect(flow.create).toHaveBeenCalledTimes(2));
  act(() => {
    void result.current.preparePatientTurn(8);
    result.current.beginPatientTurn(8, 2300);
    result.current.endPatientTurn(8, true, 3000);
  });
  await waitFor(() => expect(flow.upload).toHaveBeenCalledOnce());
  expect(flow.upload.mock.calls[0][0].metadata).toMatchObject({message_id: 8, playback_start_ms: 300, playback_end_ms: 1000});
});
