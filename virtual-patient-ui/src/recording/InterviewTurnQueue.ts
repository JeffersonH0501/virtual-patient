import type {LocalInterviewTurn} from './InterviewTurnStore';

export type TurnReceipt = {turn_media_id: string; preserved: boolean; sha256: string; metadata_hash: string};

/** One upload lane per interview, independent from the conversation request. */
export class InterviewTurnQueue {
  private pending = new Map<string, Promise<void>>();
  private failed = new Set<string>();
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
    void task.then(() => this.pending.delete(turn.id), () => this.failed.add(turn.id));
    return task;
  }

  async drain(): Promise<void> {
    await Promise.all([...this.pending.values()]);
  }
}
