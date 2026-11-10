import {getAuthHeaders} from '../auth/authHeaders';
import {API_URL} from '../../utils/request';
import {InterviewBlockStore, type LocalInterviewBlock} from '../../recording/InterviewBlockStore';
import {InterviewBlockQueue, type BlockReceipt} from '../../recording/InterviewBlockQueue';

export const blockScope = (interviewId: number): string => {
  const token = getAuthHeaders().Authorization?.split(' ')[1];
  if (!token) throw new Error('An authenticated capture account is required');
  const claims = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
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
export const subscribeBlockConnection = (id: number, listener: (online: boolean) => void) => {
  const scope = blockScope(id);
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
export const blockFetch = async (interviewId: number, path: string, init: RequestInit, scope = blockScope(interviewId)): Promise<Response> => {
  let attempts = 0;
  for (;;) {
    if (init.signal?.aborted) throw init.signal.reason;
    if (blockScope(interviewId) !== scope) throw new Error('Capture account changed');
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

export const blockJson = async <T>(interviewId: number, path: string, init: RequestInit = {}): Promise<T> => {
  const response = await blockFetch(interviewId, path, init);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.code ?? `Block request failed (${response.status})`);
  return body as T;
};

export type RemoteBlock = {block_id: string; duration_ms: number | null; metadata: LocalInterviewBlock['metadata']; sha256: string; student_video_source: string | null};
export const getBlockManifest = (id: number, signal?: AbortSignal) => blockJson<{blocks: RemoteBlock[]; duration_ms: number | null}>(id, '/recording/blocks', {signal});

const queues = new Map<string, InterviewBlockQueue>();
export const blockUploadQueue = (interviewId: number, writer: () => string | null, resumeAttempt?: string, signal?: AbortSignal) => {
  const scope = blockScope(interviewId);
  let queue = queues.get(scope);
  if (!queue) {
    const store = new InterviewBlockStore(scope);
    queue = new InterviewBlockQueue(async (block) => {
      const file = await store.original(block, Boolean(resumeAttempt));
      const form = new FormData();
      form.append('metadata', JSON.stringify(block.metadata));
      form.append('file', file);
      const response = await blockFetch(interviewId, `/recording/blocks/${block.id}`, {method: 'PUT', body: form,
        signal,
        headers: {'X-Capture-Segment': writer() ?? '', ...(resumeAttempt ? {'X-Resume-Attempt': resumeAttempt} : {})}}, scope);
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.code ?? 'Block preservation failed');
      return body as BlockReceipt;
    }, async (block) => {
      block.state = 'preserved';
      await store.put(block);
      await store.removePreserved(block).catch(() => undefined);
    });
    queues.set(scope, queue);
  }
  return queue;
};

export const forgetBlockQueue = (interviewId: number) => queues.delete(blockScope(interviewId));

export const resumeBlockInterview = async (id: number, requestId: string, force = false, signal?: AbortSignal) => {
  const recoverySignal = signal ?? (force ? AbortSignal.timeout(30_000) : undefined);
  forgetBlockQueue(id);
  const resume = await blockJson<{resume_attempt_id: string; previous_segment_id: string | null; offset_ms: number;
    previous_duration_ms: number | null; pending_patient_message_id?: number | null; retention_expires_at?: string}>(id, '/recording/resume', {
      method: 'POST', signal: recoverySignal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify({request_id: requestId}),
    });
  const store = new InterviewBlockStore(blockScope(id));
  await store.purgeExpired();
  type RecoveryMessage = {id: number; sender_type: string; message_metadata?: {client_request_id?: string}};
  const messages = {messages: [] as RecoveryMessage[]};
  for (;;) {
    const page = await blockJson<{messages: RecoveryMessage[]}>(id, messages.messages.length ? `/messages?offset=${messages.messages.length}` : '/messages', {signal: recoverySignal});
    messages.messages.push(...page.messages);
    if (page.messages.length < 100) break;
  }
  const missing = new Set<number>();
  const confirmed = new Map((await getBlockManifest(id, recoverySignal)).blocks.map((block) => [block.block_id, block]));
  const queue = blockUploadQueue(id, () => resume.previous_segment_id, resume.resume_attempt_id,
    force ? AbortSignal.any([recoverySignal!, AbortSignal.timeout(5000)]) : recoverySignal);
  for (const block of await store.list()) {
    if (Date.parse(block.expiresAt) <= Date.now()) continue;
    const remote = confirmed.get(block.id);
    if (remote?.student_video_source && Object.entries(block.metadata).every(([key, value]) =>
      JSON.stringify(value) === JSON.stringify(remote.metadata[key as keyof typeof remote.metadata]))) {
      block.state = 'preserved';
      await store.put(block);
      await store.removePreserved(block).catch(() => undefined);
      continue;
    }
    if (block.state === 'preserved') {
      block.state = 'closed';
      await store.put(block);
    }
    if (block.state === 'capturing') {
      const exchange = messages.messages.filter((message) => message.message_metadata?.client_request_id === block.requestId);
      const studentId = exchange.find((item) => item.sender_type === 'user')?.id ?? block.metadata.student_message_id ?? null;
      const patientId = exchange.find((item) => item.sender_type === 'patient')?.id ?? block.metadata.patient_message_id;
      if (!patientId) {
        await store.patch(block.id, {pendingContent: undefined});
        await store.discardUnsent(block);
        continue;
      }
      const duration = block.confirmedEndMs;
      const playback = block.metadata.patient_playback;
      const confirmedPlayback = playback && playback.start_ms < duration ? {start_ms: playback.start_ms, end_ms: duration} : null;
      const metadata = {...block.metadata, duration_ms: duration, student_message_id: studentId, patient_message_id: patientId,
        patient_playback: confirmedPlayback,
        student_speech: studentId && block.metadata.student_speech && block.metadata.student_speech.start_ms < duration
          ? {...block.metadata.student_speech, end_ms: Math.min(duration, block.metadata.student_speech.end_ms)} : null,
        student_speech_complete: !studentId || Boolean(block.metadata.student_speech && block.metadata.student_speech.end_ms <= duration),
        patient_audio_missing: !confirmedPlayback, patient_playback_complete: false, recovery: !studentId};
      Object.assign(block, await store.patch(block.id, {state: 'closed', metadata, pendingContent: undefined}));
    }
    try {
      await queue.enqueue(block);
    } catch (error) {
      if (block.metadata.student_message_id) missing.add(block.metadata.student_message_id);
      if (block.metadata.patient_message_id) missing.add(block.metadata.patient_message_id);
      // Keep incomplete originals locally; the server records explicit absence below.
      console.warn('Block recovery evidence unavailable', {interviewId: id, blockId: block.id, stage: 'recovery', error: error instanceof Error ? error.name : 'unknown'});
    }
  }
  forgetBlockQueue(id);
  const manifest = await getBlockManifest(id, recoverySignal);
  const covered = new Set(manifest.blocks.filter((block) => block.student_video_source).flatMap((block) =>
    [block.metadata.student_message_id, block.metadata.patient_message_id].filter((value): value is number => typeof value === 'number')));
  for (const message of messages.messages) {
    if (!covered.has(message.id)) missing.add(message.id);
  }
  if (missing.size) {
    await blockJson(id, '/recording/blocks/recovery', {method: 'POST',
      signal: recoverySignal,
      headers: {'Content-Type': 'application/json', 'X-Resume-Attempt': resume.resume_attempt_id}, body: JSON.stringify({missing_message_ids: [...missing]})});
  }
  const heard = manifest.blocks.some((block) => block.metadata.patient_message_id === resume.pending_patient_message_id && block.metadata.patient_playback_complete !== false);
  return {resumeAttemptId: resume.resume_attempt_id, offsetMs: manifest.duration_ms ?? 0,
    previousSegmentId: resume.previous_segment_id, previousDurationMs: resume.previous_duration_ms,
    pendingPatientMessageId: heard ? null : resume.pending_patient_message_id, retentionExpiresAt: resume.retention_expires_at};
};
