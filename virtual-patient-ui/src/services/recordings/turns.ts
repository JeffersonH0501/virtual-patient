import {getAuthHeaders} from '../auth/authHeaders';
import {handleUnauthorized} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {InterviewTurnStore, type LocalInterviewTurn} from '../../recording/InterviewTurnStore';
import {InterviewTurnQueue, type TurnReceipt} from '../../recording/InterviewTurnQueue';
import {CaptureSyncError} from '../../recording/CaptureSyncError';

/** The error code a rejected capture request carries, whether the server sent `detail` as text or as `{code}`. */
const rejectionCode = (body: {detail?: unknown}, status: number): string =>
  typeof body.detail === 'string' ? body.detail
    : (body.detail as {code?: string} | undefined)?.code ?? `Turn request failed (${status})`;

/** Largest turn original the server accepts (`TURN_VIDEO_MAX_BYTES`); the capture rotates clips long before this. */
export const TURN_ORIGINAL_MAX_BYTES = 128 * 1024 * 1024;
export const turnScope = (interviewId: number): string => {
  const token = getAuthHeaders().Authorization?.split(' ')[1];
  if (!token) throw new Error('An authenticated capture account is required');
  let claims: {sub?: unknown};
  try {
    claims = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    // A missing/expired/non-JWT token must surface as an auth error, not crash
    // the capture pipeline with a raw decode exception.
    throw new Error('An authenticated capture account is required');
  }
  if (typeof claims.sub !== 'string' || !claims.sub) throw new Error('Capture account identity is unavailable');
  return `${claims.sub}:${interviewId}`;
};

const delay = (ms: number, signal?: AbortSignal | null) => new Promise<void>((resolve, reject) => {
  if (signal?.aborted) {
    reject(signal.reason); return;
  }
  const aborted = () => {
    clearTimeout(timer); reject(signal?.reason);
  };
  const timer = setTimeout(() => {
    signal?.removeEventListener('abort', aborted); resolve();
  }, ms);
  signal?.addEventListener('abort', aborted, {once: true});
});
const connections = new Map<string, {online: boolean; listeners: Set<(online: boolean) => void>}>();
export const subscribeTurnConnection = (id: number, listener: (online: boolean) => void) => {
  const scope = turnScope(id);
  const state = connections.get(scope) ?? {online: navigator.onLine, listeners: new Set<(online: boolean) => void>()};
  connections.set(scope, state);
  state.listeners.add(listener);
  return () => {
    state.listeners.delete(listener); if (!state.listeners.size) connections.delete(scope);
  };
};
const reportConnection = (scope: string, online: boolean) => {
  const state = connections.get(scope);
  if (!state || state.online === online) return;
  state.online = online;
  for (const listener of state.listeners) listener(online);
};

/** Retry the same immutable request and return its response to the original consumer. */
export const turnFetch = async (interviewId: number, path: string, init: RequestInit, scope = turnScope(interviewId)): Promise<Response> => {
  let attempts = 0;
  for (;;) {
    if (init.signal?.aborted) throw init.signal.reason;
    if (turnScope(interviewId) !== scope) throw new Error('Capture account changed');
    if (!navigator.onLine) {
      await new Promise<void>((resolve, reject) => {
        const done = () => {
          window.removeEventListener('online', online); init.signal?.removeEventListener('abort', aborted);
        };
        const online = () => {
          done(); resolve();
        };
        const aborted = () => {
          done(); reject(init.signal?.reason);
        };
        window.addEventListener('online', online, {once: true});
        init.signal?.addEventListener('abort', aborted, {once: true});
      });
      continue;
    }
    try {
      const response = await fetch(`${API_URL}/medical-interviews/${interviewId}${path}`, {
        ...init, headers: {...getAuthHeaders(), ...init.headers}, signal: init.signal ?? AbortSignal.timeout(120_000),
      });
      if (response.status === 401) {
        await response.body?.cancel();
        handleUnauthorized();
      }
      if (![408, 429, 502, 503, 504].includes(response.status)) {
        const body = await response.arrayBuffer();
        reportConnection(scope, true);
        return new Response([204, 205, 304].includes(response.status) ? null : body,
          {status: response.status, statusText: response.statusText, headers: response.headers});
      }
      await response.body?.cancel();
    } catch (error) {
      if (init.signal?.aborted) throw error;
      if (!(error instanceof TypeError) && !(error instanceof DOMException && ['TimeoutError', 'AbortError'].includes(error.name))) throw error;
      if (error instanceof TypeError) reportConnection(scope, false);
    }
    await delay(Math.min(5000, 300 * 2 ** Math.min(attempts++, 4)), init.signal);
  }
};

export const turnJson = async <T>(interviewId: number, path: string, init: RequestInit = {}): Promise<T> => {
  const response = await turnFetch(interviewId, path, {...init, signal: init.signal ?? AbortSignal.timeout(120_000)});
  const body = await response.json();
  if (!response.ok) throw new CaptureSyncError(response.status, rejectionCode(body, response.status));
  return body as T;
};

export type RemoteTurn = {turn_media_id: string; duration_ms: number | null; message_id: number | null;
  session_clock_ms: number; metadata: LocalInterviewTurn['metadata']; sha256: string; student_video_source: string | null};
export const getTurnManifest = (id: number, signal?: AbortSignal) =>
  turnJson<{turns: RemoteTurn[]; duration_ms: number | null}>(id, '/recording/turns', {signal});

const queues = new Map<string, InterviewTurnQueue>();
export const turnUploadQueue = (interviewId: number, writer: () => string | null, resumeAttempt?: string, signal?: AbortSignal) => {
  const scope = turnScope(interviewId);
  let queue = queues.get(scope);
  if (!queue) {
    const store = new InterviewTurnStore(scope);
    queue = new InterviewTurnQueue(async (turn) => {
      const file = await store.original(turn, Boolean(resumeAttempt));
      if (file.size > TURN_ORIGINAL_MAX_BYTES) {
        // Fail at once instead of retrying a request that can never succeed; finalization declares the original missing.
        throw new Error('turn-original-too-large');
      }
      const form = new FormData();
      form.append('metadata', JSON.stringify(turn.metadata));
      form.append('video', file);
      const response = await turnFetch(interviewId, `/recording/turns/${turn.id}/video`, {method: 'PUT', body: form,
        signal,
        headers: {'X-Capture-Segment': writer() ?? '', ...(resumeAttempt ? {'X-Resume-Attempt': resumeAttempt} : {})}}, scope);
      const body = await response.json();
      // The status travels with the error so the queue can tell a retryable server fault from a rejection.
      if (!response.ok) throw new CaptureSyncError(response.status, rejectionCode(body, response.status));
      return body as TurnReceipt;
    }, async (turn) => {
      turn.state = 'preserved';
      await store.put(turn);
      await store.removePreserved(turn).catch(() => undefined);
    });
    queues.set(scope, queue);
  }
  return queue;
};

export const forgetTurnQueue = (interviewId: number) => queues.delete(turnScope(interviewId));

export const resumeTurnInterview = async (id: number, requestId: string, force = false, signal?: AbortSignal) => {
  const recoverySignal = signal ?? (force ? AbortSignal.timeout(30_000) : undefined);
  forgetTurnQueue(id);
  const resume = await turnJson<{resume_attempt_id: string; previous_segment_id: string | null; offset_ms: number;
    previous_duration_ms: number | null; pending_patient_message_id?: number | null; retention_expires_at?: string}>(id, '/recording/resume', {
      method: 'POST', signal: recoverySignal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify({request_id: requestId}),
    });
  const store = new InterviewTurnStore(turnScope(id));
  await store.purgeExpired();
  type RecoveryMessage = {id: number; sender_type: string; message_metadata?: {client_request_id?: string}};
  const messages = {messages: [] as RecoveryMessage[]};
  for (;;) {
    const page = await turnJson<{messages: RecoveryMessage[]}>(id, messages.messages.length ? `/messages?offset=${messages.messages.length}` : '/messages', {signal: recoverySignal});
    messages.messages.push(...page.messages);
    if (page.messages.length < 100) break;
  }
  const missing = new Set<number>();
  const confirmed = new Map((await getTurnManifest(id, recoverySignal)).turns.map((turn) => [turn.turn_media_id, turn]));
  const queue = turnUploadQueue(id, () => resume.previous_segment_id, resume.resume_attempt_id,
    force ? AbortSignal.any([recoverySignal!, AbortSignal.timeout(5000)]) : recoverySignal);
  for (const turn of await store.list()) {
    if (Date.parse(turn.expiresAt) <= Date.now()) continue;
    const remote = confirmed.get(turn.id);
    if (remote?.student_video_source && Object.entries(turn.metadata).every(([key, value]) =>
      JSON.stringify(value) === JSON.stringify(remote.metadata[key as keyof typeof remote.metadata]))) {
      turn.state = 'preserved';
      await store.put(turn);
      await store.removePreserved(turn).catch(() => undefined);
      continue;
    }
    if (turn.state === 'preserved') {
      turn.state = 'closed';
      await store.put(turn);
    }
    if (turn.state === 'capturing') {
      const exchange = messages.messages.filter((message) => message.message_metadata?.client_request_id === turn.requestId);
      const patient = turn.metadata.speaker === 'patient';
      const messageId = turn.metadata.message_id ?? exchange.find((item) =>
        patient ? item.sender_type === 'chatbot' || item.sender_type === 'patient' : item.sender_type === 'user')?.id;
      const duration = turn.confirmedEndMs;
      if (!turn.chunks || !duration) {
        await store.patch(turn.id, {pendingContent: undefined});
        await store.discardUnsent(turn).catch(() => undefined);
        continue;
      }
      // Without a message the fragment is kept as an idle clip; reload timing has no playback window.
      const speechStart = !patient && messageId && (turn.metadata.speech_start_ms ?? duration) < duration
        ? turn.metadata.speech_start_ms : null;
      const metadata = {...turn.metadata, duration_ms: duration, message_id: messageId ?? null, speech_start_ms: speechStart,
        ...(patient ? {playback_start_ms: null, playback_end_ms: null, playback_complete: false} : {}),
        interaction_area_snapshots: turn.metadata.interaction_area_snapshots?.filter((sample) => sample.timestampMs <= duration)};
      Object.assign(turn, await store.patch(turn.id, {state: 'closed', metadata, pendingContent: undefined}));
    }
    try {
      await queue.enqueue(turn);
    } catch (error) {
      if (turn.metadata.message_id) missing.add(turn.metadata.message_id);
      // Keep incomplete originals locally; the server records explicit absence below.
      console.warn('Turn recovery evidence unavailable', {interviewId: id, turnMediaId: turn.id, stage: 'recovery', error: error instanceof Error ? error.name : 'unknown'});
    }
  }
  forgetTurnQueue(id);
  const manifest = await getTurnManifest(id, recoverySignal);
  const covered = new Set(manifest.turns.filter((turn) => turn.student_video_source)
    .map((turn) => turn.message_id).filter((value): value is number => typeof value === 'number'));
  for (const message of messages.messages) {
    if (!covered.has(message.id)) missing.add(message.id);
  }
  if (missing.size) {
    await turnJson(id, '/recording/turns/recovery', {method: 'POST',
      signal: recoverySignal,
      headers: {'Content-Type': 'application/json', 'X-Resume-Attempt': resume.resume_attempt_id}, body: JSON.stringify({missing_message_ids: [...missing]})});
  }
  return {resumeAttemptId: resume.resume_attempt_id, offsetMs: manifest.duration_ms ?? 0,
    previousSegmentId: resume.previous_segment_id, previousDurationMs: resume.previous_duration_ms,
    pendingPatientMessageId: resume.pending_patient_message_id,
    recoveredPatientMessageId: resume.pending_patient_message_id != null && covered.has(resume.pending_patient_message_id)
      ? resume.pending_patient_message_id : null,
    retentionExpiresAt: resume.retention_expires_at};
};
