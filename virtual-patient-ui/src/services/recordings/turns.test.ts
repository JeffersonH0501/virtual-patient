import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {turnFetch, turnJson, subscribeTurnConnection, resumeTurnInterview, turnUploadQueue, forgetTurnQueue} from './turns';
import {sendMessage} from '../interviews/sendMessage';
import {completeInterview} from '../interviews/completeInterview';
import {createHypothesis} from '../hypotheses/createHypothesis';
import * as authRequests from '../../utils/apiFetch';
import type {LocalInterviewTurn} from '../../recording/InterviewTurnStore';
import type {StudentCaptureTiming} from '../../types/recording';

const state = vi.hoisted(() => ({owner: 'one', rows: new Map<string, LocalInterviewTurn>(), original: vi.fn()}));
vi.mock('../auth/sessionIdentity', () => ({getSessionAccountId: () => state.owner}));
vi.mock('../../recording/InterviewTurnStore', () => ({InterviewTurnStore: class {
  async purgeExpired() {
    return;
  }
  async put(turn: LocalInterviewTurn) {
    state.rows.set(turn.id, structuredClone(turn));
  }
  async removePreserved(turn: LocalInterviewTurn) {
    state.rows.delete(turn.id);
  }
  async discardUnsent(turn: LocalInterviewTurn) {
    const current = state.rows.get(turn.id)!;
    if (current.pendingContent || current.metadata.message_id) throw new Error('Only an unsent intervention can be discarded');
    state.rows.delete(turn.id);
  }
  async original(turn: LocalInterviewTurn) {
    return state.original(turn);
  }
  async list() {
    return [...state.rows.values()].map((item) => structuredClone(item));
  }
  async patch(id: string, patch: Partial<LocalInterviewTurn>) {
    const current = state.rows.get(id)!;
    const next = {...current, ...patch, metadata: {...current.metadata, ...patch.metadata}};
    state.rows.set(id, next); return next;
  }
}}));
beforeEach(() => {
  vi.useFakeTimers(); state.owner = 'one'; state.rows.clear(); state.original.mockReset();
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
});

it('keeps the original request and consumer across a lost response', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('Synthetic lost response')).mockResolvedValueOnce(new Response('{}'));
  vi.stubGlobal('fetch', fetch);
  const body = JSON.stringify({client_request_id: 'stable-id'});
  const response = turnFetch(1, '/messages', {method: 'POST', body});
  await vi.advanceTimersByTimeAsync(300);
  expect((await response).status).toBe(200);
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls.map((call) => call[1].body)).toEqual([body, body]);
});

it.each(['hypotheses', 'completion', 'resume'] as const)('bounds interactive %s retries with one shared deadline', async (operation) => {
  const controller = new AbortController();
  const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(controller.signal);
  const fetch = vi.fn().mockRejectedValue(new TypeError('Synthetic network failure'));
  vi.stubGlobal('fetch', fetch);
  const pending = operation === 'resume' ? resumeTurnInterview(7, 'stable-resume')
    : operation === 'completion' ? completeInterview('7') : createHypothesis('7', [{hypothesisText: 'Synthetic', hypothesisOrder: 1}]);
  const failure = expect(pending).rejects.toHaveProperty('name', 'TimeoutError');
  await vi.advanceTimersByTimeAsync(300);
  controller.abort(new DOMException('Synthetic deadline', 'TimeoutError'));
  await failure;
  expect(timeout).toHaveBeenCalledWith(120_000);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('does not automatically repeat a content conflict', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({detail: {code: 'turn_media_conflict'}}), {status: 409}));
  vi.stubGlobal('fetch', fetch);
  await expect(turnJson(1, '/recording/turns/id/video')).rejects.toThrow('turn_media_conflict');
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('uses the shared expired-session recovery when capture requests receive HTTP 401', async () => {
  const unauthorized = vi.spyOn(authRequests, 'handleUnauthorized').mockImplementation(() => {
    throw Object.assign(new Error('Unauthorized'), {status: 401});
  });
  const fetch = vi.fn().mockResolvedValue(new Response('{}', {status: 401}));
  vi.stubGlobal('fetch', fetch);
  await expect(turnJson(1, '/recording/segments')).rejects.toHaveProperty('status', 401);
  expect(unauthorized).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledOnce();
});

it('recovers a truncated response body and pauses only the affected interview', async () => {
  const first = new Response('{}');
  vi.spyOn(first, 'arrayBuffer').mockRejectedValueOnce(new TypeError('Synthetic truncated response'));
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(new Response('{}')));
  const affected = vi.fn(); const other = vi.fn();
  const remove = subscribeTurnConnection(1, affected); const removeOther = subscribeTurnConnection(2, other);
  const response = turnFetch(1, '/messages', {method: 'POST', body: 'same-content'});
  await vi.advanceTimersByTimeAsync(300);
  expect((await response).ok).toBe(true);
  expect(affected.mock.calls).toEqual([[false], [true]]);
  expect(other).not.toHaveBeenCalled();
  remove(); removeOther();
});

it('stops an old account request before another attempt', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('Synthetic lost response'));
  vi.stubGlobal('fetch', fetch);
  const request = turnFetch(1, '/messages', {method: 'POST'});
  const assertion = expect(request).rejects.toThrow('Capture account changed');
  state.owner = 'two';
  await vi.advanceTimersByTimeAsync(300);
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('persists the message key before sending and binds the response to that turn', async () => {
  state.rows.set('turn', {id: 'turn', state: 'capturing', scope: 'one:1', chunks: 2, metadata: {}} as LocalInterviewTurn);
  const fetch = vi.fn(async () => {
    const turn = state.rows.get('turn')!;
    expect(turn.requestId).toBe('stable-message');
    expect(turn.pendingContent).toBe('Synthetic question');
    expect(turn.chunks).toBe(2);
    return new Response(JSON.stringify({messages: [{id: 1, sender_type: 'user'}, {id: 2, sender_type: 'patient'}], new_message_ids: [1, 2]}));
  });
  vi.stubGlobal('fetch', fetch);
  await sendMessage('1', 'Synthetic question', 'stable-message', 'capture', {
    turn_media_id: 'turn', capture_scope: 'one:1', start_ms: 0, end_ms: 600,
  } as StudentCaptureTiming);
  expect(state.rows.get('turn')?.metadata.message_id).toBe(1);
  expect(state.rows.get('turn')?.pendingContent).toBeUndefined();
});

it('bounds message retries and preserves the local turn and request key for an explicit retry', async () => {
  vi.spyOn(AbortSignal, 'timeout').mockImplementation((milliseconds) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(new DOMException('Message deadline exceeded', 'TimeoutError')), milliseconds);
    return controller.signal;
  });
  state.rows.set('turn', {id: 'turn', state: 'capturing', scope: 'one:1', chunks: 2, metadata: {}} as LocalInterviewTurn);
  const fetch = vi.fn(async () => new Response('{}', {status: 503}));
  vi.stubGlobal('fetch', fetch);
  const timing = {turn_media_id: 'turn', capture_scope: 'one:1', start_ms: 0, end_ms: 600} as StudentCaptureTiming;
  let failure: unknown;
  const pending = sendMessage('1', 'Synthetic question', 'stable-message', 'capture', timing).catch((error) => {
 failure = error;
});
  await vi.advanceTimersByTimeAsync(119_999);
  expect(failure).toBeUndefined();
  await vi.advanceTimersByTimeAsync(1);
  expect(failure).toMatchObject({name: 'TimeoutError'});
  await pending;
  const attempts = fetch.mock.calls.length;
  await vi.advanceTimersByTimeAsync(60_000);
  expect(fetch).toHaveBeenCalledTimes(attempts);
  expect(state.rows.get('turn')).toMatchObject({state: 'capturing', requestId: 'stable-message', pendingContent: 'Synthetic question', chunks: 2});
  fetch.mockImplementation(async () => new Response(JSON.stringify({messages: [{id: 1, sender_type: 'user'}, {id: 2, sender_type: 'patient'}], new_message_ids: [1, 2]})));
  await sendMessage('1', 'Synthetic question', 'stable-message', 'capture', timing);
  expect(fetch.mock.calls.every((call) => JSON.parse((call as unknown as [string, RequestInit])[1].body as string).client_request_id === 'stable-message')).toBe(true);
  expect(state.rows.get('turn')?.metadata.message_id).toBe(1);
  expect(state.rows.get('turn')?.pendingContent).toBeUndefined();
});

const recoveryRoutes = (known = false, patient = false) => {
  const turn: LocalInterviewTurn = {id: 'local', scope: 'one:1', requestId: 'stable', state: 'closed', mimeType: 'video/webm',
    chunks: 2, confirmedEndMs: 2000, expiresAt: new Date(Date.now() + 86400_000).toISOString(),
    metadata: {capture_attempt_id: 'capture', order: 0, duration_ms: 2000, message_id: 5, speaker: 'student', session_clock_ms: 0}};
  if (patient) {
    turn.state = 'capturing';
    turn.metadata.speaker = 'patient';
    delete turn.metadata.message_id;
  }
  state.rows.set(turn.id, turn);
  let uploaded = known;
  const gaps: number[] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    let body: unknown;
    if (url.endsWith('/recording/resume')) body = {resume_attempt_id: 'resume', previous_segment_id: 'capture', offset_ms: 0, pending_patient_message_id: 10};
    else if (url.endsWith('/messages')) {
body = {messages: [{id: 5, sender_type: 'user'},
      {id: 10, sender_type: 'patient', message_metadata: {client_request_id: 'stable'}}]};
} else if (url.endsWith('/recording/turns')) {
      body = {duration_ms: uploaded ? 2000 : null, turns: uploaded ? [{
        turn_media_id: 'local', message_id: patient ? 10 : 5, session_clock_ms: 0, metadata: turn.metadata,
        student_video_source: '/original', sha256: 'a'.repeat(64), duration_ms: 2000}] : []};
    } else if (url.endsWith('/recording/turns/local/video')) {
      uploaded = true;
      expect(new Headers(init.headers).get('X-Resume-Attempt')).toBe('resume');
      if (patient) {
expect(JSON.parse(String((init.body as FormData).get('metadata')))).toMatchObject({
        speaker: 'patient', message_id: 10, playback_complete: false, playback_start_ms: null, playback_end_ms: null,
      });
}
      body = {turn_media_id: 'local', preserved: true, sha256: 'a'.repeat(64), metadata_hash: 'b'.repeat(64)};
    } else if (url.endsWith('/recording/turns/recovery')) {
      gaps.push(...JSON.parse(String(init.body)).missing_message_ids); body = {recorded: true};
    } else throw new Error('Unexpected recovery endpoint');
    return new Response(JSON.stringify(body));
  });
  vi.stubGlobal('fetch', fetch);
  return {fetch, gaps};
};

it('recovers an available turn before calibration', async () => {
  recoveryRoutes();
  state.original.mockResolvedValue(new File(['original'], 'turn.webm', {type: 'video/webm'}));
  const resume = await resumeTurnInterview(1, 'resume-request');
  expect(resume.offsetMs).toBe(2000);
  expect(state.original).toHaveBeenCalledTimes(1);
  expect(state.rows.size).toBe(0);
});

it('recovers patient camera by its exchange ID without fabricating a playback window', async () => {
  const {gaps} = recoveryRoutes(false, true);
  state.original.mockResolvedValue(new File(['original'], 'turn.webm', {type: 'video/webm'}));
  const resume = await resumeTurnInterview(1, 'resume-request');
  expect(resume.recoveredPatientMessageId).toBe(10);
  expect(gaps).toEqual([5]);
  expect(state.rows.size).toBe(0);
});

it('keeps unreadable local originals and records absence without blocking the resume dialog', async () => {
  const {gaps} = recoveryRoutes();
  state.original.mockRejectedValue(new Error('Synthetic missing file'));
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  await resumeTurnInterview(1, 'resume-request');
  expect(gaps).toEqual([5, 10]);
  expect(state.rows.get('local')?.state).toBe('closed');
});

it('reconciles a confirmed original after reload without uploading the same file again', async () => {
  const {fetch} = recoveryRoutes(true);
  await resumeTurnInterview(1, 'resume-request');
  expect(state.original).not.toHaveBeenCalled();
  expect(fetch.mock.calls.some((call) => call[1].method === 'PUT')).toBe(false);
  expect(state.rows.size).toBe(0);
});

it('records lost evidence when resuming in another browser with no local checkpoint', async () => {
  const {gaps} = recoveryRoutes();
  state.rows.clear();
  await resumeTurnInterview(1, 'resume-request');
  expect(gaps).toEqual([5, 10]);
  expect(state.original).not.toHaveBeenCalled();
});

it('repeats the resume after a reload without sending an original twice', async () => {
  const {fetch} = recoveryRoutes();
  state.original.mockResolvedValue(new File(['original'], 'turn.webm', {type: 'video/webm'}));
  await resumeTurnInterview(1, 'resume-request');
  // The same request after another reload (or a double click): the server answers the same attempt and nothing is pending locally.
  await resumeTurnInterview(1, 'resume-request');
  expect(fetch.mock.calls.filter((call) => call[1].method === 'PUT')).toHaveLength(1);
  expect(state.original).toHaveBeenCalledTimes(1);
});

it('carries the status and the code of a rejected request so callers can tell a verdict from a fault', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({detail: {code: 'stale_capture'}}), {status: 409}))
    .mockResolvedValueOnce(new Response(JSON.stringify({detail: 'Interview not found'}), {status: 404}))
    .mockResolvedValueOnce(new Response(JSON.stringify({}), {status: 500})));
  await expect(turnJson(1, '/recording/segments')).rejects.toMatchObject({status: 409, code: 'stale_capture', transient: false});
  await expect(turnJson(1, '/recording/segments')).rejects.toMatchObject({status: 404, code: 'Interview not found', transient: false});
  await expect(turnJson(1, '/recording/segments')).rejects.toMatchObject({status: 500, transient: true});
});

it('retries a busy server by itself and a slow upload does not create a second request', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('{}', {status: 503}))
    .mockResolvedValueOnce(new Response('{}', {status: 504}))
    .mockResolvedValueOnce(new Response('{"segment_id":"s"}'));
  vi.stubGlobal('fetch', fetch);
  const answer = turnJson(1, '/recording/segments', {method: 'POST', body: 'same-start-request'});
  await vi.advanceTimersByTimeAsync(300 + 600);
  await expect(answer).resolves.toEqual({segment_id: 's'});
  expect(fetch.mock.calls.map((call) => call[1].body)).toEqual(['same-start-request', 'same-start-request', 'same-start-request']);
});

it('keeps an original that the server failed to store and sends it again when asked, then releases it', async () => {
  const turn: LocalInterviewTurn = {id: 'late', scope: 'one:1', requestId: 'r', state: 'closed', mimeType: 'video/webm',
    chunks: 2, confirmedEndMs: 2000, expiresAt: new Date(Date.now() + 86400_000).toISOString(),
    metadata: {capture_attempt_id: 'capture', order: 0, duration_ms: 2000, message_id: 5, speaker: 'student', session_clock_ms: 0}};
  state.rows.set(turn.id, turn);
  state.original.mockResolvedValue(new File(['original'], 'turn.webm', {type: 'video/webm'}));
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({detail: 'Internal error'}), {status: 500}))
    .mockResolvedValueOnce(new Response(JSON.stringify({turn_media_id: 'late', preserved: true, sha256: 'a'.repeat(64), metadata_hash: 'b'.repeat(64)})));
  vi.stubGlobal('fetch', fetch);
  forgetTurnQueue(1);
  const queue = turnUploadQueue(1, () => 'capture');
  await expect(queue.enqueue(turn)).rejects.toMatchObject({status: 500});
  // The failure left the local original untouched.
  expect(state.rows.get('late')?.state).toBe('closed');
  expect(queue.retryTransient()).toBe(1);
  await queue.drain();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(state.rows.has('late')).toBe(false);
  forgetTurnQueue(1);
});

it('bounds every network step of forced recovery with one cancellation signal', async () => {
  const {fetch} = recoveryRoutes();
  state.rows.clear();
  await resumeTurnInterview(1, 'forced-request', true);
  expect(fetch.mock.calls.every(([, init]) => Boolean(init.signal))).toBe(true);
  expect(new Set(fetch.mock.calls.map(([, init]) => init.signal)).size).toBe(1);
});

it('cancels retry backoff without waiting for another network attempt', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('Synthetic disconnected network'));
  vi.stubGlobal('fetch', fetch);
  const controller = new AbortController();
  const request = turnFetch(1, '/messages', {method: 'POST', signal: controller.signal});
  const assertion = expect(request).rejects.toThrow('Synthetic recovery cancellation');
  await vi.advanceTimersByTimeAsync(1);
  controller.abort(new Error('Synthetic recovery cancellation'));
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(1);
});
