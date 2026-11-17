import {InterviewTurnRecorder} from './InterviewTurnRecorder';
import {InterviewTurnStore, type LocalInterviewTurn, type TurnCaptureMetadata} from './InterviewTurnStore';
import {CaptureSyncError} from './CaptureSyncError';
import {forgetTurnQueue, getTurnManifest, turnJson, turnScope, turnUploadQueue} from '../services/recordings/turns';
import type {RecordingStatus, SpeechTiming, StudentCaptureTiming} from '../types/recording';

/** Audio before the detected onset kept in the analysis window, since detection lags the first syllable. */
const SPEECH_PREROLL_MS = 300;
/** Frames kept after the playback boundary so frame quantization does not cut off the measured window. */
const PLAYBACK_TAIL_MS = 120;
/**
 * A clip that waits for the student to speak grows for as long as the student stays silent, and the server refuses
 * originals above a fixed size. Such a wait is split into consecutive idle clips well before that ceiling (about 2.5
 * minutes is a few tens of MB even with a high-bitrate camera).
 */
const MAX_IDLE_CLIP_MS = 150_000;
const IDLE_CHECK_MS = 5_000;
/** Finalization gives up only after this long without any pending upload finishing, not after a fixed total time. */
const UPLOAD_STALL_MS = 180_000;
/** A manifest or finalize request that is still unanswered after this long fails with a retryable error. */
const FINALIZE_REQUEST_TIMEOUT_MS = 120_000;
/** Extra upload rounds finalization spends on originals that failed for a transient reason before declaring them missing. */
const FINALIZE_RETRY_ROUNDS = 2;
/** One reconnection probe waits this long for the server; an unanswered probe is a transient failure, not a verdict. */
const RECONNECT_PROBE_TIMEOUT_MS = 15_000;
const RECONNECT_BASE_DELAY_MS = 1_000;
const RECONNECT_MAX_DELAY_MS = 30_000;

/**
 * The server's verdict on a capture it will no longer accept writes from. Reconnecting never clears these:
 * `capture-superseded` is recovered through the resume flow, `capture-closed` means the recording or interview ended.
 */
const definitiveCaptureCode = (error: unknown): string | null => {
  if (!(error instanceof CaptureSyncError) || error.transient || error.status === 401) return null;
  if (error.status !== 409) return 'capture-closed';
  return error.code === 'capture_closed' ? 'capture-closed' : 'capture-superseded';
};

export type CaptureState = {status: RecordingStatus; syncPending: boolean; errorCode: string | null; captureId: string | null;
  /** The transport dropped and capture is paused until the server confirms this capture is still current. */
  reconnecting: boolean};

export type CaptureInputs = {
  interviewId?: number;
  cameraStream: MediaStream | null;
  microphoneStream: MediaStream | null;
  resumeAttemptId?: string | null;
  recoveredPatientMessageId?: number | null;
  /** Reply that plays as soon as capture is armed: the greeting, or a reply pending on resume. */
  initialPatientMessageId?: number | null;
  missingMessageIds?: number[];
  studentMessageIds?: number[];
  patientMessageIds?: number[];
};

type Clip = {recorder: InterviewTurnRecorder; regions: Record<string, number>[]; speechStartMs: number | null; messageId: number | null};

const speakerOf = (clip: Clip | null) => clip?.recorder.turn.metadata.speaker;
const isReplyClip = (clip: Clip | null, messageId: number): clip is Clip =>
  speakerOf(clip) === 'patient' && clip!.messageId === messageId;

/**
 * Continuous per-turn capture: from arming until sealing exactly one clip is
 * open. Student clips (camera + microphone) run from the moment the floor
 * returns to the student until the utterance is submitted; patient clips
 * (camera only) cover the wait and the reply. Clips no message owns are kept
 * as idle clips so the replay never loses time.
 */
export class InterviewCapture {
  private writer: string | null = null;
  private expiresAt: string | null = null;
  private geometry: string | null = null;
  private devices: {camera?: string; microphone?: string} | null = null;
  private clockMs: number;
  private order = 0;
  private clip: Clip | null = null;
  private submitted: Clip | null = null;
  private playback: {messageId: number; start: number; interrupted: boolean} | null = null;
  private closedPatientMessages = new Set<number>();
  /** First reply (greeting or reply pending on resume): the recording and clock start when it starts playing. */
  private awaitingFirstReply: number | null = null;
  private blocked: string | null = null;
  private offline = !navigator.onLine;
  private sealed = false;
  private disposed = false;
  private serial: Promise<unknown> = Promise.resolve();
  private startRequest: string | null = null;
  private startBody: string | null = null;
  private startAbort: AbortController | null = null;
  private idleTimer: ReturnType<typeof setInterval> | null = null;
  /** Advances on every disconnection, so a probe that was in flight when the link dropped again is not trusted. */
  private connectionEpoch = 0;
  private reconnection: Promise<void> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  /** The resume flow took over this capture; it must neither probe nor write to the server any more. */
  private handedOff = false;
  /** The server accepted the finalization: its recording is closed on purpose and completion carries its own verdict. */
  private finalized = false;
  private state: CaptureState = {status: 'idle', syncPending: false, errorCode: null, captureId: null, reconnecting: false};

  constructor(private inputs: () => CaptureInputs, private onChange: (state: CaptureState) => void, initialOffsetMs = 0) {
    this.clockMs = initialOffsetMs;
  }

  // ---- state -------------------------------------------------------------

  get snapshot() {
    return this.state;
  }

  get isBlocked() {
    return Boolean(this.blocked);
  }

  get isSealed() {
    return this.sealed;
  }

  private set(patch: Partial<CaptureState>) {
    this.state = {...this.state, ...patch};
    if (!this.disposed) this.onChange(this.state);
  }

  private settle() {
    this.set({syncPending: Boolean(this.blocked) || this.offline || !navigator.onLine});
  }

  private run<T>(operation: () => Promise<T>): Promise<T | undefined> {
    const next = this.serial.then(operation).catch(() => {
      if (!this.disposed) this.fail();
      return undefined;
    });
    this.serial = next;
    return next;
  }

  private fail = () => this.invalidate('temporary-storage-failed');

  invalidate(code: string) {
    if (this.playback) this.playback.interrupted = true;
    this.blocked = code;
    this.clip?.recorder.pause();
    this.set({errorCode: code, syncPending: true});
  }

  /** Attempt to clear a storage block and restart capture without losing the conversation. */
  async attemptStorageRecovery(): Promise<boolean> {
    if (!this.blocked || this.blocked !== 'temporary-storage-failed') return false;
    try {
      // Still disconnected: the recorder stays paused and the reconnection resumes it once the server confirms this capture.
      // Otherwise try to resume the recorder that failed.
      if (!this.offline && !this.clip?.recorder.resume()) {
        // If the recorder can't resume, the only option is to stop for recovery.
        return false;
      }
      this.blocked = null;
      this.set({errorCode: null, status: 'recording'});
      this.settle();
      if (this.offline) void this.goOnline();
      return true;
    } catch {
      return false;
    }
  }

  elapsedAt = () => this.clockMs + (this.clip?.recorder.elapsed() ?? 0);

  // ---- environment -------------------------------------------------------

  geometryNow() {
    const settings = this.inputs().cameraStream?.getVideoTracks()[0]?.getSettings();
    return JSON.stringify({viewport_width: innerWidth, viewport_height: innerHeight, device_pixel_ratio: devicePixelRatio,
      screen_width: screen.width, screen_height: screen.height, orientation: innerWidth >= innerHeight ? 'landscape' : 'portrait',
      video_width: settings?.width, video_height: settings?.height});
  }

  devicesMatch() {
    const camera = this.inputs().cameraStream?.getVideoTracks()[0];
    const microphone = this.inputs().microphoneStream?.getAudioTracks()[0];
    return Boolean(camera && microphone && camera.readyState !== 'ended' && microphone.readyState !== 'ended' &&
      camera.id === this.devices?.camera && microphone.id === this.devices?.microphone);
  }

  canContinueWithCurrentSetup() {
    return !this.blocked && this.devicesMatch() && this.geometry === this.geometryNow();
  }

  /** Geometry or device changes invalidate the calibration the capture relies on. */
  checkEnvironment() {
    if (this.sealed || !this.geometry) return;
    if (this.geometry !== this.geometryNow()) this.invalidate('capture-geometry-changed');
    if (!this.devicesMatch()) this.invalidate('capture-device-changed');
  }

  deviceEnded() {
    if (!this.sealed) this.invalidate('capture-device-changed');
  }

  /** The transport dropped: pause the recorder (the compensated clock excludes the pause) and wait for the link. */
  goOffline() {
    if (this.handedOff) return;
    this.connectionEpoch += 1;
    if (this.playback) this.playback.interrupted = true;
    this.offline = true;
    this.clip?.recorder.pause();
    this.set({syncPending: true, reconnecting: true});
  }

  /**
   * The transport is back. Capture continues only after the server confirms this capture is still the writer of an
   * open interview. Concurrent triggers (browser event, transport report, retry timer) share one attempt.
   */
  goOnline(): Promise<void> {
    this.reconnection ??= this.reestablish().finally(() => {
      this.reconnection = null;
    });
    return this.reconnection;
  }

  /**
   * Replaying the start request is the ownership check: `POST /recording/segments` is idempotent on its request ID,
   * so it creates nothing, and it answers 409 `stale_capture` when this segment was sealed or replaced
   * and 409 `capture_closed` when the recording or interview already ended.
   */
  private async confirmWriter(id: number) {
    const segment = await turnJson<{segment_id: string}>(id, '/recording/segments', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: this.startBody,
      signal: AbortSignal.timeout(RECONNECT_PROBE_TIMEOUT_MS)});
    if (segment.segment_id !== this.writer) throw new CaptureSyncError(409, 'stale_capture');
  }

  private async reestablish() {
    const id = this.inputs().interviewId;
    // Nothing to confirm without a started segment; a device or geometry change needs recalibration, which no
    // reconnection can provide.
    if (!id || !this.writer || !this.startBody || this.handedOff ||
        (this.blocked && this.blocked !== 'temporary-storage-failed')) {
      if (this.state.reconnecting) this.set({reconnecting: false});
      return;
    }
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.finalized) {
      // A closed recording is the expected state here; there is nothing left to confirm or resume.
      this.offline = false;
      this.set({reconnecting: false});
      this.settle();
      return;
    }
    try {
      for (;;) {
        const epoch = this.connectionEpoch;
        await this.confirmWriter(id);
        // The link dropped again while the probe was in flight: its answer says nothing about the new outage.
        if (epoch === this.connectionEpoch) break;
      }
    } catch (error) {
      if (this.disposed || this.handedOff) return;
      const code = definitiveCaptureCode(error);
      if (code) {
        this.offline = false;
        this.set({reconnecting: false});
        this.invalidate(code);
        return;
      }
      // Transient (timeout, dropped link, server busy): stay paused, keep every local original and probe again.
      this.scheduleReconnect();
      return;
    }
    if (this.disposed || this.handedOff) return;
    this.reconnectAttempts = 0;
    this.offline = false;
    // A recorder that cannot resume has failed on its own storage, which is a different, user-visible block.
    if (!this.blocked && !this.sealed && this.state.status === 'recording' && this.clip && !this.clip.recorder.resume()) this.fail();
    this.set({reconnecting: false});
    this.settle();
    // Originals that could not be sent during the outage are still stored locally: send them again now.
    turnUploadQueue(id, () => this.writer).retryTransient();
  }

  private scheduleReconnect() {
    if (this.reconnectTimer !== null) return;
    const delay = Math.min(RECONNECT_MAX_DELAY_MS, RECONNECT_BASE_DELAY_MS * 2 ** this.reconnectAttempts);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.disposed) void this.goOnline();
    }, delay);
  }

  sampleRegion() {
    const clip = this.clip;
    const rect = document.querySelector<HTMLElement>('[data-interaction-area]')?.getBoundingClientRect();
    if (!rect || !clip || this.sealed) return;
    const region = {xNormalized: Math.max(0, rect.x) / innerWidth, yNormalized: Math.max(0, rect.y) / innerHeight,
      widthNormalized: Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.x)) / innerWidth,
      heightNormalized: Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.y)) / innerHeight};
    if (!region.widthNormalized || !region.heightNormalized) return;
    const last = clip.regions[clip.regions.length - 1];
    if (last && Object.entries(region).every(([key, value]) => last[key] === value)) return;
    clip.regions.push({timestampMs: clip.recorder.elapsed(), ...region});
    void clip.recorder.checkpoint({interaction_area_snapshots: [...clip.regions]}).catch(this.fail);
  }

  // ---- clip chain --------------------------------------------------------

  private async open(speaker: 'student' | 'patient', requestId: string = crypto.randomUUID(), messageId: number | null = null) {
    const {interviewId, cameraStream, microphoneStream} = this.inputs();
    if (!interviewId || !cameraStream || !microphoneStream || !this.writer) throw new Error('Capture devices are unavailable');
    if (!this.devicesMatch()) return this.invalidate('capture-device-changed');
    if (this.geometry !== this.geometryNow()) return this.invalidate('capture-geometry-changed');
    const store = new InterviewTurnStore(turnScope(interviewId));
    const turn: LocalInterviewTurn = {id: crypto.randomUUID(), scope: store.scope, requestId,
      mimeType: '', chunks: 0, confirmedEndMs: 0, expiresAt: this.expiresAt!, state: 'capturing',
      metadata: {capture_attempt_id: this.writer, order: this.order++, session_clock_ms: this.clockMs, speaker,
        ...(messageId == null ? {} : {message_id: messageId})}};
    const recorder = new InterviewTurnRecorder(store, turn, this.fail);
    await recorder.start(cameraStream, speaker === 'student' ? microphoneStream : undefined);
    if (this.disposed) {
      await recorder.stop(); return;
    }
    this.clip = {recorder, regions: [], speechStartMs: null, messageId};
    if (this.blocked || this.offline || !navigator.onLine || this.state.status === 'paused') recorder.pause();
    this.sampleRegion();
  }

  /** Close the open clip at this instant and open the next one in its place. */
  private async rotate(next: 'student' | 'patient' | null, requestId?: string, messageId: number | null = null): Promise<Clip | null> {
    const previous = this.clip;
    this.clip = null;
    if (previous) this.clockMs = (previous.recorder.turn.metadata.session_clock_ms ?? this.clockMs) + previous.recorder.elapsed();
    await Promise.all([previous?.recorder.stop(), next && !this.sealed ? this.open(next, requestId, messageId) : undefined]);
    return previous;
  }

  private async close(clip: Clip, extra: Partial<TurnCaptureMetadata> = {}) {
    const {metadata} = clip.recorder.turn;
    if ((extra.message_id ?? clip.messageId) == null && !clip.recorder.turn.chunks) {
      // An idle clip too short to produce a fragment leaves no evidence to keep.
      await clip.recorder.stop();
      if (!clip.recorder.turn.chunks) {
        await clip.recorder.store.discardUnsent(clip.recorder.turn).catch(() => undefined);
        return;
      }
    }
    // Every field is explicit: the local record keeps earlier checkpoints (an onset of an utterance that was never sent).
    const owned = clip.messageId != null;
    const closed = await clip.recorder.close({capture_attempt_id: this.writer!, order: metadata.order!,
      speaker: metadata.speaker!, session_clock_ms: metadata.session_clock_ms!, message_id: clip.messageId,
      duration_ms: clip.recorder.elapsed(), interaction_area_snapshots: clip.regions,
      speech_start_ms: owned && metadata.speaker === 'student' ? clip.speechStartMs : null,
      playback_start_ms: null, playback_end_ms: null, playback_complete: false, ...extra});
    const id = this.inputs().interviewId;
    // A rejected original is missing evidence, declared at finalization; it must not stop the conversation.
    if (!id) return;
    void turnUploadQueue(id, () => this.writer).enqueue(closed).catch((error: unknown) =>
      console.warn('Turn original was not preserved', {interviewId: id, turnMediaId: closed.id, error: error instanceof Error ? error.message : 'unknown'}));
  }

  // ---- long idle clips ---------------------------------------------------

  private startIdleRotation() {
    this.idleTimer ??= setInterval(() => this.rotateLongIdleClip(), IDLE_CHECK_MS);
  }

  private stopIdleRotation() {
    if (this.idleTimer !== null) clearInterval(this.idleTimer);
    this.idleTimer = null;
  }

  /** Close an idle student clip that has waited too long and open the next one in its place; speech is never split. */
  private rotateLongIdleClip() {
    void this.run(async () => {
      const clip = this.clip;
      if (this.sealed || this.blocked || this.offline || this.state.status !== 'recording' || !clip || this.submitted) return;
      if (speakerOf(clip) !== 'student' || clip.speechStartMs !== null || clip.messageId !== null) return;
      if (clip.recorder.elapsed() < MAX_IDLE_CLIP_MS) return;
      const previous = await this.rotate('student');
      if (previous) await this.close(previous);
    });
  }

  // ---- lifecycle ---------------------------------------------------------

  /** Open (or reuse) the capture segment and start the first student clip. */
  arm() {
    return this.run(async () => {
      const inputs = this.inputs();
      if (!inputs.interviewId || !inputs.cameraStream || !inputs.microphoneStream) return;
      const id = inputs.interviewId;
      this.set({syncPending: true});
      if (this.geometry && this.geometry !== this.geometryNow()) return this.invalidate('capture-geometry-changed');
      this.blocked = null;
      this.set({errorCode: null});
      if (!this.writer) {
        try {
          forgetTurnQueue(id);
          await new InterviewTurnStore(turnScope(id)).purgeExpired();
          this.startRequest ??= crypto.randomUUID();
          this.startBody ??= JSON.stringify({request_id: this.startRequest, resume_attempt_id: inputs.resumeAttemptId ?? undefined,
            capture_config: {mediaTransport: 'per_turn_v1', geometry: JSON.parse(this.geometryNow())}});
          this.startAbort = new AbortController();
          const segment = await turnJson<{segment_id: string; retention_expires_at: string; offset_ms: number}>(id, '/recording/segments', {
            method: 'POST', signal: this.startAbort.signal, headers: {'Content-Type': 'application/json'}, body: this.startBody});
          if (this.disposed) return;
          this.writer = segment.segment_id;
          this.expiresAt = segment.retention_expires_at;
          this.clockMs = segment.offset_ms;
          this.geometry = JSON.stringify(JSON.parse(this.startBody).capture_config.geometry);
          this.devices = {camera: inputs.cameraStream.getVideoTracks()[0]?.id, microphone: inputs.microphoneStream.getAudioTracks()[0]?.id};
          this.set({captureId: segment.segment_id});
        } catch {
          if (this.disposed || this.startAbort?.signal.aborted) return;
          this.set({status: 'failed'});
          return this.invalidate('capture-start-failed');
        }
        if (this.geometry !== this.geometryNow()) return this.invalidate('capture-geometry-changed');
      }
      this.set({status: 'recording'});
      this.startIdleRotation();
      if (!this.clip && !this.sealed) {
        // The greeting opens the timeline: its clip exists, bound, before playback can start.
        const reply = inputs.initialPatientMessageId;
        const playsNow = reply != null && reply !== inputs.recoveredPatientMessageId && !this.closedPatientMessages.has(reply);
        if (playsNow) this.awaitingFirstReply = reply;
        else await this.open('student');
      }
      this.settle();
    });
  }

  pause() {
    if (this.playback) this.playback.interrupted = true;
    this.clip?.recorder.pause();
    this.set({status: 'paused'});
  }

  resume() {
    if (this.blocked || (this.clip && !this.clip.recorder.resume())) return;
    this.set({status: 'recording'});
  }

  /** Close the open clip so the capture can be finalized; idle time up to now is kept. */
  async seal(): Promise<boolean> {
    this.stopIdleRotation();
    await this.serial;
    this.sealed = true;
    await this.run(async () => {
      const clip = this.clip;
      const submitted = this.submitted;
      this.submitted = null;
      this.playback = null;
      if (clip) {
        await this.rotate(null);
        await this.close(clip);
      }
      if (submitted) await this.close(submitted);
    });
    if (this.blocked) return false;
    this.set({status: 'paused', syncPending: false});
    return true;
  }

  /** Reopen capture after the student cancels the closing dialog. */
  async reopen() {
    if (!this.devicesMatch() || this.geometry !== this.geometryNow()) {
      this.invalidate('capture-device-changed'); return;
    }
    this.sealed = false;
    this.startIdleRotation();
    this.set({status: 'recording', syncPending: true});
    await this.run(async () => {
      if (!this.clip) await this.open('student');
      this.settle();
    });
  }

  /** `onProgress` receives the fraction (0 to 1) of the saving work done: pending uploads first, then verification. */
  async finalize(preserveOnly = false, onProgress?: (fraction: number) => void): Promise<boolean> {
    try {
      if (!await this.seal()) return false;
      onProgress?.(0);
      const id = this.inputs().interviewId!;
      const queue = turnUploadQueue(id, () => this.writer);
      // A pending original that is still uploading is waited for; only a drain that makes no progress for
      // UPLOAD_STALL_MS gives up, so a large original on a slow connection does not fail by total time alone.
      let timer: ReturnType<typeof setTimeout> | undefined;
      let restartStallTimer = () => undefined as void;
      const stalled = new Promise<never>((_, reject) => {
        restartStallTimer = () => {
          clearTimeout(timer);
          timer = setTimeout(() => reject(new Error('Upload timeout')), UPLOAD_STALL_MS);
        };
        restartStallTimer();
      });
      let reported = 0;
      const drainUploads = () => Promise.race([
        queue.drain((settled, total) => {
          restartStallTimer();
          reported = Math.max(reported, total ? 0.85 * (settled / total) : 0.85);
          onProgress?.(reported);
        }),
        stalled,
      ]);
      try {
        await drainUploads();
        // An original that failed for a transient reason is still stored locally: try it again before it is declared missing.
        for (let round = 0; round < FINALIZE_RETRY_ROUNDS && queue.retryTransient() > 0; round += 1) await drainUploads();
      } finally {
        clearTimeout(timer);
      }
      if (preserveOnly) return true;
      onProgress?.(0.9);
      const inputs = this.inputs();
      // Both requests are idempotent on the server, so a timeout is retried by the user without side effects.
      const manifest = await getTurnManifest(id, AbortSignal.timeout(FINALIZE_REQUEST_TIMEOUT_MS));
      const covered = new Set(manifest.turns.filter((item) => item.student_video_source)
        .map((item) => item.message_id).filter((messageId): messageId is number => typeof messageId === 'number'));
      const missing = [...new Set([...(inputs.missingMessageIds ?? []),
        ...[...(inputs.studentMessageIds ?? []), ...(inputs.patientMessageIds ?? [])].filter((messageId) => !covered.has(messageId))])];
      await turnJson(id, '/recording/turns/finalize', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Capture-Segment': this.writer!},
        signal: AbortSignal.timeout(FINALIZE_REQUEST_TIMEOUT_MS),
        body: JSON.stringify({turn_media_ids: manifest.turns.map((item) => item.turn_media_id), missing_message_ids: missing})});
      this.finalized = true;
      onProgress?.(1);
      return true;
    } catch (error) {
      const timedOut = (error instanceof Error && error.message === 'Upload timeout') ||
        (error instanceof DOMException && error.name === 'TimeoutError');
      this.set({errorCode: timedOut ? 'finalize-timeout' : 'finalize-failed', syncPending: false});
      return false;
    }
  }

  /** Stop without closing: open fragments stay local for the recovery upload. */
  async stopForRecovery() {
    this.stopIdleRotation();
    this.sealed = true;
    // The resume flow seals this segment on the server; a late reconnection probe must not report that as a failure.
    this.handedOff = true;
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.startAbort?.abort();
    this.set({syncPending: true});
    await this.serial;
    try {
      await this.clip?.recorder.stop();
    } catch {
      this.fail();
    }
    this.clip = null;
    this.set({status: 'paused'});
  }

  /** Strict Mode remounts reattach the same capture before pending work resolves. */
  attach() {
    this.disposed = false;
  }

  dispose() {
    this.disposed = true;
    this.stopIdleRotation();
    const clip = this.clip;
    queueMicrotask(() => {
      if (this.disposed) void clip?.recorder.stop().catch(() => undefined);
    });
  }

  // ---- conversation events ----------------------------------------------

  /** The latest onset before submission marks where the utterance begins. */
  markSpeechStart(at = performance.now()) {
    void this.run(async () => {
      const clip = this.clip;
      if (speakerOf(clip) !== 'student' || !clip) return;
      clip.speechStartMs = Math.max(0, clip.recorder.elapsed(at) - SPEECH_PREROLL_MS);
      await clip.recorder.checkpoint({speech_start_ms: clip.speechStartMs});
    });
  }

  /** The utterance was committed: the microphone clip ends and the camera-only wait begins. */
  submitStudentTurn(requestId: string) {
    if (this.sealed) return;
    void this.run(async () => {
      if (speakerOf(this.clip) === 'patient') return;
      this.submitted = await this.rotate('patient', requestId);
    });
  }

  /** Nothing was sent or no reply will play: idle clips keep the time and the student gets a new clip. */
  returnFloorToStudent() {
    void this.run(async () => {
      const submitted = this.submitted;
      this.submitted = null;
      if (speakerOf(this.clip) === 'patient' && this.clip?.messageId == null) {
        const wait = await this.rotate('student');
        if (wait) await this.close(wait);
      }
      if (submitted) await this.close(submitted);
    });
  }

  async prepareStudentTurn(timing?: SpeechTiming): Promise<StudentCaptureTiming> {
    await this.serial;
    const clip = this.submitted ?? (speakerOf(this.clip) === 'student' ? this.clip : null);
    return {turn_media_id: clip?.recorder.turn.id, capture_scope: clip?.recorder.store.scope,
      start_ms: 0, end_ms: clip?.recorder.elapsed(timing?.endedAt) ?? 0,
      input_source: timing?.inputSource ?? 'microphone', timing_source: 'turn_media', timing_quality: 'provisional', patient_roi_snapshots: []};
  }

  recordStudentTurn(messageId: number) {
    void this.run(async () => {
      const clip = this.submitted;
      this.submitted = null;
      if (!clip) return;
      clip.messageId = messageId;
      await this.close(clip);
    });
  }

  /** Bind the reply to the camera-only clip before it plays. */
  async preparePatientTurn(messageId: number) {
    if (this.sealed || this.closedPatientMessages.has(messageId) || this.inputs().recoveredPatientMessageId === messageId) return;
    if (this.awaitingFirstReply === messageId) return;
    // Bound synchronously when possible: playback may start before queued work runs.
    const bind = () => {
      const clip = this.clip;
      if (speakerOf(clip) !== 'patient' || !clip || (clip.messageId != null && clip.messageId !== messageId)) return null;
      clip.messageId = messageId;
      return clip;
    };
    bind();
    await this.run(async () => {
      if (this.closedPatientMessages.has(messageId)) return;
      const clip = bind();
      if (clip) return clip.recorder.checkpoint({message_id: messageId});
      // A reply not preceded by a submission: the open student clip becomes idle.
      const idle = await this.rotate('patient', undefined, messageId);
      if (idle) await this.close(idle);
    });
  }

  beginPatientTurn(messageId: number, at = performance.now()) {
    if (this.awaitingFirstReply === messageId && !this.clip) {
      // The timeline starts here: the first clip opens with the patient's voice.
      this.awaitingFirstReply = null;
      this.playback = {messageId, start: 0, interrupted: Boolean(this.blocked || this.offline)};
      void this.run(() => this.open('patient', undefined, messageId));
      return;
    }
    const clip = this.clip;
    if (!isReplyClip(clip, messageId)) return;
    this.playback = {messageId, start: clip.recorder.elapsed(at), interrupted: Boolean(this.blocked || this.offline)};
  }

  endPatientTurn(messageId: number, complete: boolean, at = performance.now(), continuous = complete) {
    if (this.awaitingFirstReply === messageId) {
      // The first reply never played (written delivery): the recording starts with the student.
      this.awaitingFirstReply = null;
      this.closedPatientMessages.add(messageId);
      void this.run(() => this.open('student'));
      return;
    }
    if (!this.clip && this.playback?.messageId === messageId) {
      // The first clip is still opening; settle the reply once it exists.
      void this.run(async () => this.endPatientTurn(messageId, complete, at, continuous));
      return;
    }
    const clip = this.clip;
    if (!isReplyClip(clip, messageId) || this.closedPatientMessages.has(messageId)) return;
    const window = this.playback;
    this.playback = null;
    const end = clip.recorder.elapsed(at);
    const bounded = window?.messageId === messageId && !window.interrupted && continuous && end > window.start;
    this.closedPatientMessages.add(messageId);
    // The floor returns at once; an onset during the rotation is queued and lands at the new clip's start.
    void this.run(async () => {
      if (bounded) await new Promise<void>((resolve) => setTimeout(resolve, PLAYBACK_TAIL_MS));
      if (this.clip === clip) await this.rotate('student');
      await this.close(clip, {
        playback_start_ms: bounded ? window.start : null, playback_end_ms: bounded ? end : null,
        playback_complete: Boolean(bounded && complete)});
    });
  }
}
