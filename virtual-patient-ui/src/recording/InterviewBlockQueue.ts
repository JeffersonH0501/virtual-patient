import type {LocalInterviewBlock} from './InterviewBlockStore';

export type BlockReceipt = {block_id: string; preserved: boolean; sha256: string; metadata_hash: string};

/** One upload lane per interview, independent from the conversation request. */
export class InterviewBlockQueue {
  private pending = new Map<string, Promise<void>>();
  private failed = new Set<string>();
  private tail: Promise<void> = Promise.resolve();

  constructor(private upload: (block: LocalInterviewBlock) => Promise<BlockReceipt>,
    private preserve: (block: LocalInterviewBlock) => Promise<void>) {}

  enqueue(block: LocalInterviewBlock): Promise<void> {
    if (block.state !== 'closed') return Promise.reject(new Error('Only closed blocks can be uploaded'));
    const previous = this.pending.get(block.id);
    if (previous && !this.failed.has(block.id)) return previous;
    this.failed.delete(block.id);
    const task = this.tail.catch(() => undefined).then(async () => {
      const receipt = await this.upload(block);
      if (!receipt.preserved || receipt.block_id !== block.id || !/^[a-f0-9]{64}$/.test(receipt.sha256) ||
        !/^[a-f0-9]{64}$/.test(receipt.metadata_hash)) throw new Error('Invalid block preservation receipt');
      await this.preserve(block);
    });
    this.pending.set(block.id, task);
    this.tail = task;
    void task.then(() => this.pending.delete(block.id), () => this.failed.add(block.id));
    return task;
  }

  async drain(): Promise<void> {
    await Promise.all([...this.pending.values()]);
  }
}
