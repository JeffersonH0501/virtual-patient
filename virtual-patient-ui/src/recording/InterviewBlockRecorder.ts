import {selectVideoMimeType} from '../utils/mediaRecorder';
import {InterviewBlockStore, type BlockMetadata, type LocalInterviewBlock} from './InterviewBlockStore';

/** A single muxed original spans student speech, technical wait and patient playback. */
export class InterviewBlockRecorder {
  private recorder: MediaRecorder | null = null;
  private origin: number | null = null;
  private writes: Promise<void> = Promise.resolve();
  private failure: unknown;
  private closing?: Promise<LocalInterviewBlock>;
  private pauses: {start: number; end: number | null}[] = [];
  private stoppedAt: number | null = null;

  constructor(readonly store: InterviewBlockStore, readonly block: LocalInterviewBlock,
    private onStorageFailure: (error: unknown) => void) {}

  async start(camera: MediaStream, microphone: MediaStream): Promise<void> {
    if (this.recorder) throw new Error('Block recorder already started');
    const tracks = [...camera.getVideoTracks(), ...microphone.getAudioTracks()];
    if (!tracks.some((track) => track.kind === 'video') || !tracks.some((track) => track.kind === 'audio')) {
      throw new Error('Block capture requires camera and microphone tracks');
    }
    const mimeType = selectVideoMimeType();
    if (!mimeType) throw new Error('A supported camera/microphone recording format is unavailable');
    this.block.mimeType = mimeType;
    await this.store.create(this.block);
    const recorder = new MediaRecorder(new MediaStream(tracks), {mimeType});
    this.recorder = recorder;
    recorder.addEventListener('dataavailable', (event) => {
      if (!event.data.size) return;
      const endMs = this.elapsed();
      this.writes = this.writes.then(() => this.store.append(this.block, event.data, endMs));
      void this.writes.catch((error) => {
        if (!this.failure) {
          this.failure = error;
          this.pause();
          this.onStorageFailure(error);
        }
      });
    });
    recorder.addEventListener('error', (event) => {
      this.failure = new Error(`Block recorder failed: ${event.type}`);
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

  async checkpoint(metadata: Partial<BlockMetadata>): Promise<void> {
    if (this.block.state !== 'capturing' || this.closing) throw new Error('Closed block metadata is immutable');
    this.writes = this.writes.then(async () => {
      Object.assign(this.block, await this.store.patch(this.block.id, {metadata}));
    });
    await this.writes;
  }

  async flush(): Promise<void> {
    await this.writes;
  }

  close(metadata: BlockMetadata): Promise<LocalInterviewBlock> {
    if (this.closing) return this.closing;
    this.closing = this.finish(metadata);
    return this.closing;
  }

  private async finish(metadata: BlockMetadata): Promise<LocalInterviewBlock> {
    const recorder = this.recorder;
    if (!recorder) throw new Error('Block capture has not started');
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
    if (!this.block.chunks) throw new Error('No local original was confirmed');
    Object.assign(this.block, await this.store.patch(this.block.id, {metadata: {...metadata, duration_ms: durationMs}, state: 'closed'}));
    return this.block;
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
