import {selectVideoMimeType} from '../utils/mediaRecorder';
import {InterviewTurnStore, type TurnCaptureMetadata, type LocalInterviewTurn} from './InterviewTurnStore';

/** One original per turn, with a microphone track only during student speech. */
export class InterviewTurnRecorder {
  private recorder: MediaRecorder | null = null;
  private origin: number | null = null;
  private writes: Promise<void> = Promise.resolve();
  private failure: unknown;
  private closing?: Promise<LocalInterviewTurn>;
  private pauses: {start: number; end: number | null}[] = [];
  private stoppedAt: number | null = null;

  constructor(readonly store: InterviewTurnStore, readonly turn: LocalInterviewTurn,
    private onStorageFailure: (error: unknown) => void) {}

  async start(camera: MediaStream, microphone?: MediaStream): Promise<void> {
    if (this.recorder) throw new Error('Turn recorder already started');
    const video = camera.getVideoTracks();
    const audio = microphone?.getAudioTracks() ?? [];
    if (!video.length || (microphone && !audio.length)) {
      throw new Error('Required turn capture tracks are unavailable');
    }
    const mimeType = selectVideoMimeType(audio.length > 0);
    if (!mimeType) throw new Error('A supported turn recording format is unavailable');
    this.turn.mimeType = mimeType;
    await this.store.create(this.turn);
    const recorder = new MediaRecorder(new MediaStream([...video, ...audio]), {mimeType});
    this.recorder = recorder;
    recorder.addEventListener('dataavailable', (event) => {
      if (!event.data.size) return;
      const endMs = this.elapsed();
      this.writes = this.writes.then(() => this.store.append(this.turn, event.data, endMs));
      void this.writes.catch((error) => {
        if (!this.failure) {
          this.failure = error;
          this.pause();
          this.onStorageFailure(error);
        }
      });
    });
    recorder.addEventListener('error', (event) => {
      this.failure = new Error(`Turn recorder failed: ${event.type}`);
      this.onStorageFailure(this.failure);
    });
    await new Promise<void>((resolve, reject) => {
      recorder.addEventListener('start', () => {
        this.origin = performance.now(); resolve();
      }, {once: true});
      recorder.addEventListener('error', reject, {once: true});
      try {
        recorder.start(1000);
      } catch (error) {
        reject(error);
      }
    });
  }

  elapsed(at = performance.now()): number {
    if (this.origin === null) return 0;
    const end = Math.min(at, this.stoppedAt ?? at);
    const pausedMs = this.pauses.reduce((total, pause) =>
      total + Math.max(0, Math.min(end, pause.end ?? end) - pause.start), 0);
    return Math.max(0, Math.round(end - this.origin - pausedMs));
  }

  pause(): void {
    if (this.recorder?.state === 'recording') {
      this.pauses.push({start: performance.now(), end: null});
      this.recorder.pause();
    }
  }

  resume(): boolean {
    if (this.recorder?.state === 'paused' && !this.failure) {
      this.pauses[this.pauses.length - 1].end = performance.now();
      this.recorder.resume();
    }
    return !this.failure && this.recorder?.state === 'recording';
  }

  async checkpoint(metadata: Partial<TurnCaptureMetadata>): Promise<void> {
    if (this.turn.state !== 'capturing' || this.closing) throw new Error('Closed turn metadata is immutable');
    this.writes = this.writes.then(async () => {
      Object.assign(this.turn, await this.store.patch(this.turn.id, {metadata}));
    });
    await this.writes;
  }

  close(metadata: TurnCaptureMetadata): Promise<LocalInterviewTurn> {
    if (this.closing) return this.closing;
    this.closing = this.finish(metadata);
    return this.closing;
  }

  private async finish(metadata: TurnCaptureMetadata): Promise<LocalInterviewTurn> {
    const recorder = this.recorder;
    if (!recorder) throw new Error('Turn capture has not started');
    const durationMs = this.elapsed();
    this.stoppedAt ??= performance.now();
    if (recorder.state !== 'inactive') {
      await new Promise<void>((resolve, reject) => {
        recorder.addEventListener('stop', () => resolve(), {once: true});
        recorder.addEventListener('error', reject, {once: true});
        recorder.stop();
      });
    }
    await this.writes;
    if (this.failure) throw this.failure;
    if (!this.turn.chunks) throw new Error('No local original was confirmed');
    Object.assign(this.turn, await this.store.patch(this.turn.id, {metadata: {...metadata, duration_ms: durationMs}, state: 'closed'}));
    return this.turn;
  }

  async stop(): Promise<void> {
    const recorder = this.recorder;
    this.stoppedAt ??= performance.now();
    if (recorder && recorder.state !== 'inactive') {
      await new Promise<void>((resolve) => {
        recorder.addEventListener('stop', () => resolve(), {once: true});
        recorder.stop();
      });
    }
    await this.writes;
  }
}
