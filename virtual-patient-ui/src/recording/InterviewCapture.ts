import {InterviewTurnRecorder} from './InterviewTurnRecorder';
import {InterviewTurnStore, type LocalInterviewTurn, type TurnCaptureMetadata} from './InterviewTurnStore';
import {forgetTurnQueue, getTurnManifest, turnJson, turnScope, turnUploadQueue} from '../services/recordings/turns';
import type {RecordingStatus, SpeechTiming, StudentCaptureTiming} from '../types/recording';

/** Audio before the detected onset kept in the analysis window, since detection lags the first syllable. */
const SPEECH_PREROLL_MS = 300;
/** Frames kept after the playback boundary so frame quantization does not cut off the measured window. */
const PLAYBACK_TAIL_MS = 120;

export type CaptureState = {status: RecordingStatus; syncPending: boolean; errorCode: string | null; captureId: string | null};

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
  private state: CaptureState = {status: 'idle', syncPending: false, errorCode: null, captureId: null};

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
      // Try to resume the recorder that failed.
      const resumed = this.clip?.recorder.resume();
      if (resumed) {
        this.blocked = null;
        this.set({errorCode: null, syncPending: false, status: 'recording'});
        return true;
      }
      // If the recorder can't resume, the only option is to stop for recovery.
      return false;
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

  goOffline() {
    if (this.playback) this.playback.interrupted = true;
    this.offline = true;
    this.clip?.recorder.pause();
    this.set({syncPending: true});
  }

  async goOnline() {
    const id = this.inputs().interviewId;
    if (!id || this.sealed || this.blocked) return;
    try {
      const state = await turnJson<{active_segment_id: string | null}>(id, '/capture/state');
      if (state.active_segment_id !== this.writer) throw new Error('stale_capture');
      if (this.sealed || this.blocked) return;
      this.offline = false;
      this.clip?.recorder.resume();
      this.set({syncPending: false});
    } catch {
      this.fail();
    }
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
    this.set({status: 'recording', syncPending: true});
    await this.run(async () => {
      if (!this.clip) await this.open('student');
      this.settle();
    });
  }

  async finalize(preserveOnly = false): Promise<boolean> {
    try {
      if (!await this.seal()) return false;
      const id = this.inputs().interviewId!;
      // Drain with a 60-second timeout so participants aren't stuck indefinitely if upload stalls.
      const drainTimeout = new Promise<void>((_, reject) => 
        setTimeout(() => reject(new Error('Upload timeout')), 60000)
      );
      await Promise.race([
        turnUploadQueue(id, () => this.writer).drain(),
        drainTimeout
      ]);
      if (preserveOnly) return true;
      const inputs = this.inputs();
      const manifest = await getTurnManifest(id);
      const covered = new Set(manifest.turns.filter((item) => item.student_video_source)
        .map((item) => item.message_id).filter((messageId): messageId is number => typeof messageId === 'number'));
      const missing = [...new Set([...(inputs.missingMessageIds ?? []),
        ...[...(inputs.studentMessageIds ?? []), ...(inputs.patientMessageIds ?? [])].filter((messageId) => !covered.has(messageId))])];
      await turnJson(id, '/recording/turns/finalize', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Capture-Segment': this.writer!},
        body: JSON.stringify({turn_media_ids: manifest.turns.map((item) => item.turn_media_id), missing_message_ids: missing})});
      return true;
    } catch (error) {
      this.set({errorCode: error instanceof Error && error.message === 'Upload timeout' 
        ? 'finalize-timeout' : 'finalize-failed', syncPending: false});
      return false;
    }
  }

  /** Stop without closing: open fragments stay local for the recovery upload. */
  async stopForRecovery() {
    this.sealed = true;
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
