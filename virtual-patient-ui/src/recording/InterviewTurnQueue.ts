import {CaptureSyncError} from './CaptureSyncError';
import type {LocalInterviewTurn} from './InterviewTurnStore';

export type TurnReceipt = {turn_media_id: string; preserved: boolean; sha256: string; metadata_hash: string};

/** One upload lane per interview, independent from the conversation request. */
export class InterviewTurnQueue {
  private pending = new Map<string, Promise<void>>();
  private failed = new Map<string, {turn: LocalInterviewTurn; error: unknown}>();
  private tail: Promise<void> = Promise.resolve();

  constructor(private upload: (turn: LocalInterviewTurn) => Promise<TurnReceipt>,
    private preserve: (turn: LocalInterviewTurn) => Promise<void>) {}

  enqueue(turn: LocalInterviewTurn): Promise<void> {
    if (turn.state !== 'closed') return Promise.reject(new Error('Only closed turns can be uploaded'));
    const previous = this.pending.get(turn.id);
    if (previous && !this.failed.has(turn.id)) return previous;
    this.failed.delete(turn.id);
    const task = this.tail.catch(() => undefined).then(async () => {
      const receipt = await this.upload(turn);
      if (!receipt.preserved || receipt.turn_media_id !== turn.id || !/^[a-f0-9]{64}$/.test(receipt.sha256) ||
        !/^[a-f0-9]{64}$/.test(receipt.metadata_hash)) throw new Error('Invalid turn preservation receipt');
      await this.preserve(turn);
    });
    this.pending.set(turn.id, task);
    this.tail = task;
    void task.then(() => this.pending.delete(turn.id), (error: unknown) => this.failed.set(turn.id, {turn, error}));
    return task;
  }

  /**
   * Send again the originals that failed because of a transient server or transport fault. They are still stored
   * locally, so a retry loses nothing; a rejection (conflict, stale capture, invalid file) is left failed so
   * finalization or the resume flow decides. The server accepts an identical original again as a no-op.
   * Returns how many uploads were restarted.
   */
  retryTransient(): number {
    let restarted = 0;
    for (const {turn, error} of [...this.failed.values()]) {
      if (!(error instanceof CaptureSyncError) || !error.transient) continue;
      void this.enqueue(turn).catch(() => undefined);
      restarted += 1;
    }
    return restarted;
  }

  /** Wait for every upload to settle; rejected originals are declared missing by finalization.
   *  `onProgress` receives how many of the pending uploads have settled and how many are awaited. */
  async drain(onProgress?: (settled: number, total: number) => void): Promise<void> {
    const tasks = [...this.pending.values()];
    let settled = 0;
    onProgress?.(0, tasks.length);
    await Promise.allSettled(tasks.map((task) => task.then(() => undefined, () => undefined).then(() => {
      settled += 1;
      onProgress?.(settled, tasks.length);
    })));
  }
}
