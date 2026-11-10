import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {blockFetch, blockJson, subscribeBlockConnection, resumeBlockInterview} from './blocks';
import {sendMessage} from '../interviews/sendMessage';
import type {LocalInterviewBlock} from '../../recording/InterviewBlockStore';
import type {StudentCaptureTiming} from '../../types/recording';

const state = vi.hoisted(() => ({owner: 'one', rows: new Map<string, LocalInterviewBlock>(), coordinator: vi.fn(), original: vi.fn()}));
vi.mock('../auth/authHeaders', () => ({getAuthHeaders: () => ({Authorization: `Bearer header.${btoa(JSON.stringify({sub: state.owner}))}.signature`})}));
vi.mock('../../recording/CaptureCoordinator', () => ({captureCoordinator: state.coordinator}));
vi.mock('../../recording/InterviewBlockStore', () => ({InterviewBlockStore: class {
  async purgeExpired() {
    return;
  }
  async put(block: LocalInterviewBlock) {
    state.rows.set(block.id, structuredClone(block));
  }
  async removePreserved(block: LocalInterviewBlock) {
    state.rows.delete(block.id);
  }
  async discardUnsent(block: LocalInterviewBlock) {
    const current = state.rows.get(block.id)!;
    if (current.pendingContent || current.metadata.student_message_id || current.metadata.patient_message_id) throw new Error('Only an unsent intervention can be discarded');
    state.rows.delete(block.id);
  }
  async original(block: LocalInterviewBlock) {
    return state.original(block);
  }
  async list() {
    return [...state.rows.values()].map((item) => structuredClone(item));
  }
  async patch(id: string, patch: Partial<LocalInterviewBlock>) {
    const current = state.rows.get(id)!;
    const next = {...current, ...patch, metadata: {...current.metadata, ...patch.metadata}};
    state.rows.set(id, next); return next;
  }
}}));
beforeEach(() => {
  vi.useFakeTimers(); state.owner = 'one'; state.rows.clear(); state.coordinator.mockReset(); state.original.mockReset();
});
afterEach(() => {
  vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks();
});

it('keeps the original request and consumer across a lost response', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new TypeError('Synthetic lost response')).mockResolvedValueOnce(new Response('{}'));
  vi.stubGlobal('fetch', fetch);
  const body = JSON.stringify({client_request_id: 'stable-id'});
  const response = blockFetch(1, '/messages', {method: 'POST', body});
  await vi.advanceTimersByTimeAsync(300);
  expect((await response).status).toBe(200);
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch.mock.calls.map((call) => call[1].body)).toEqual([body, body]);
});

it('does not automatically repeat a content conflict', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({detail: {code: 'block_content_conflict'}}), {status: 409}));
  vi.stubGlobal('fetch', fetch);
  await expect(blockJson(1, '/recording/blocks/id')).rejects.toThrow('block_content_conflict');
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('recovers a truncated response body and pauses only the affected interview', async () => {
  const first = new Response('{}');
  vi.spyOn(first, 'arrayBuffer').mockRejectedValueOnce(new TypeError('Synthetic truncated response'));
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(new Response('{}')));
  const affected = vi.fn(); const other = vi.fn();
  const remove = subscribeBlockConnection(1, affected); const removeOther = subscribeBlockConnection(2, other);
  const response = blockFetch(1, '/messages', {method: 'POST', body: 'same-content'});
  await vi.advanceTimersByTimeAsync(300);
  expect((await response).ok).toBe(true);
  expect(affected.mock.calls).toEqual([[false], [true]]);
  expect(other).not.toHaveBeenCalled();
  remove(); removeOther();
});

it('stops an old account request before another attempt', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('Synthetic lost response'));
  vi.stubGlobal('fetch', fetch);
  const request = blockFetch(1, '/messages', {method: 'POST'});
  const assertion = expect(request).rejects.toThrow('Capture account changed');
  state.owner = 'two';
  await vi.advanceTimersByTimeAsync(300);
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('persists the message key and speech window before sending and binds the existing response to that block', async () => {
  state.rows.set('block', {id: 'block', state: 'capturing', scope: 'one:1', chunks: 2, metadata: {}} as LocalInterviewBlock);
  const fetch = vi.fn(async () => {
    const block = state.rows.get('block')!;
    expect(block.requestId).toBe('stable-message');
    expect(block.pendingContent).toBe('Synthetic question');
    expect(block.metadata.student_speech).toEqual({start_ms: 10, end_ms: 600});
    expect(block.chunks).toBe(2);
    return new Response(JSON.stringify({messages: [{id: 1, sender_type: 'user'}, {id: 2, sender_type: 'patient'}], new_message_ids: [1, 2]}));
  });
  vi.stubGlobal('fetch', fetch);
  await sendMessage('1', 'Synthetic question', 'stable-message', 'capture', {
    block_id: 'block', block_scope: 'one:1', start_ms: 10, end_ms: 600,
  } as StudentCaptureTiming);
  expect(state.rows.get('block')?.metadata.student_message_id).toBe(1);
  expect(state.rows.get('block')?.metadata.patient_message_id).toBe(2);
  expect(state.rows.get('block')?.pendingContent).toBeUndefined();
  expect(state.coordinator).not.toHaveBeenCalled();
});

const recoveryRoutes = (known = false) => {
  const block: LocalInterviewBlock = {id: 'local', scope: 'one:1', requestId: 'stable', state: 'closed', mimeType: 'video/webm',
    chunks: 2, confirmedEndMs: 2000, expiresAt: new Date(Date.now() + 86400_000).toISOString(),
    metadata: {capture_attempt_id: 'capture', order: 0, duration_ms: 2000, student_message_id: null,
      patient_message_id: 10, student_speech: null, patient_playback: {start_ms: 100, end_ms: 1800},
      patient_audio_missing: false, recovery: false, patient_playback_complete: true}};
  state.rows.set(block.id, block);
  let uploaded = known;
  const gaps: number[] = [];
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    let body: unknown;
    if (url.endsWith('/recording/resume')) body = {resume_attempt_id: 'resume', previous_segment_id: 'capture', offset_ms: 0, pending_patient_message_id: 10};
    else if (url.endsWith('/messages')) body = {messages: [{id: 10, sender_type: 'patient'}]};
    else if (url.endsWith('/recording/blocks')) {
      body = {duration_ms: uploaded ? 2000 : null, blocks: uploaded ? [{
        block_id: 'local', metadata: block.metadata, student_video_source: '/original', sha256: 'a'.repeat(64), duration_ms: 2000}] : []};
    } else if (url.endsWith('/recording/blocks/local')) {
      uploaded = true;
      expect(new Headers(init.headers).get('X-Resume-Attempt')).toBe('resume');
      body = {block_id: 'local', preserved: true, sha256: 'a'.repeat(64), metadata_hash: 'b'.repeat(64)};
    } else if (url.endsWith('/recording/blocks/recovery')) {
      gaps.push(...JSON.parse(String(init.body)).missing_message_ids); body = {recorded: true};
    } else throw new Error('Unexpected recovery endpoint');
    return new Response(JSON.stringify(body));
  });
  vi.stubGlobal('fetch', fetch);
  return {fetch, gaps};
};

it('recovers an available block before calibration and recognizes its already delivered patient message', async () => {
  recoveryRoutes();
  state.original.mockResolvedValue(new File(['original'], 'block.webm', {type: 'video/webm'}));
  const resume = await resumeBlockInterview(1, 'resume-request');
  expect(resume.pendingPatientMessageId).toBeNull();
  expect(resume.offsetMs).toBe(2000);
  expect(state.original).toHaveBeenCalledTimes(1);
  expect(state.rows.size).toBe(0);
});

it('keeps unreadable local originals and records absence without blocking the resume dialog', async () => {
  const {gaps} = recoveryRoutes();
  state.original.mockRejectedValue(new Error('Synthetic missing file'));
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  const resume = await resumeBlockInterview(1, 'resume-request');
  expect(resume.pendingPatientMessageId).toBe(10);
  expect(gaps).toEqual([10]);
  expect(state.rows.get('local')?.state).toBe('closed');
});

it('reconciles a confirmed original after reload without uploading the same file again', async () => {
  const {fetch} = recoveryRoutes(true);
  await resumeBlockInterview(1, 'resume-request');
  expect(state.original).not.toHaveBeenCalled();
  expect(fetch.mock.calls.some((call) => call[1].method === 'PUT')).toBe(false);
  expect(state.rows.size).toBe(0);
});

it('records lost evidence when resuming in another browser with no local checkpoint', async () => {
  const {gaps} = recoveryRoutes();
  state.rows.clear();
  const resume = await resumeBlockInterview(1, 'resume-request');
  expect(resume.pendingPatientMessageId).toBe(10);
  expect(gaps).toEqual([10]);
  expect(state.original).not.toHaveBeenCalled();
});

it('marks playback unavailable when its checkpoint is beyond the durable original', async () => {
  const {fetch} = recoveryRoutes();
  const block = state.rows.get('local')!;
  block.state = 'capturing';
  block.confirmedEndMs = 100;
  block.metadata.patient_playback = {start_ms: 100, end_ms: 100};
  state.original.mockResolvedValue(new File(['partial'], 'block.webm', {type: 'video/webm'}));
  await resumeBlockInterview(1, 'resume-request');
  const upload = fetch.mock.calls.find((call) => call[1].method === 'PUT')!;
  const metadata = JSON.parse(String((upload[1].body as FormData).get('metadata')));
  expect(metadata.patient_playback).toBeNull();
  expect(metadata.patient_audio_missing).toBe(true);
  expect(metadata.patient_playback_complete).toBe(false);
});

it('reconciles a pending exchange after the first hundred messages', async () => {
  const {fetch} = recoveryRoutes();
  const base = fetch.getMockImplementation()!;
  const block = state.rows.get('local')!;
  block.state = 'capturing';
  block.metadata.patient_message_id = undefined;
  fetch.mockImplementation(async (url, init) => {
    if (url.endsWith('/messages')) return new Response(JSON.stringify({messages: Array.from({length: 100}, (_, index) => ({id: index + 1000, sender_type: 'user'}))}));
    if (url.endsWith('/messages?offset=100')) return new Response(JSON.stringify({messages: [{id: 10, sender_type: 'patient', message_metadata: {client_request_id: 'stable'}}]}));
    return base(url, init);
  });
  state.original.mockResolvedValue(new File(['partial'], 'block.webm', {type: 'video/webm'}));
  await resumeBlockInterview(1, 'resume-request');
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/messages?offset=100'))).toBe(true);
  expect(state.original).toHaveBeenCalledTimes(1);
});

it('bounds every network step of forced recovery with one cancellation signal', async () => {
  const {fetch} = recoveryRoutes();
  state.rows.clear();
  await resumeBlockInterview(1, 'forced-request', true);
  expect(fetch.mock.calls.every(([, init]) => Boolean(init.signal))).toBe(true);
  expect(new Set(fetch.mock.calls.map(([, init]) => init.signal)).size).toBe(1);
});

it('cancels retry backoff without waiting for another network attempt', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('Synthetic disconnected network'));
  vi.stubGlobal('fetch', fetch);
  const controller = new AbortController();
  const request = blockFetch(1, '/messages', {method: 'POST', signal: controller.signal});
  const assertion = expect(request).rejects.toThrow('Synthetic recovery cancellation');
  await vi.advanceTimersByTimeAsync(1);
  controller.abort(new Error('Synthetic recovery cancellation'));
  await assertion;
  expect(fetch).toHaveBeenCalledTimes(1);
});
