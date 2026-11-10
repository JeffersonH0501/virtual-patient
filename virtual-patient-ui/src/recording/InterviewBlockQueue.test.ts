import {describe, expect, it, vi} from 'vitest';
import {InterviewBlockQueue} from './InterviewBlockQueue';
import type {LocalInterviewBlock} from './InterviewBlockStore';

const block = (id: string) => ({id, state: 'closed'} as LocalInterviewBlock);
const receipt = (id: string) => ({block_id: id, preserved: true, sha256: 'a'.repeat(64), metadata_hash: 'b'.repeat(64)});

describe('InterviewBlockQueue', () => {
  it('deduplicates an original and keeps another interview independent of a slow upload', async () => {
    let finish!: () => void;
    const slow = new Promise<void>((resolve) => {
 finish = resolve;
});
    const preserve = vi.fn();
    const upload = vi.fn(async (item: LocalInterviewBlock) => {
await slow; return receipt(item.id);
});
    const first = new InterviewBlockQueue(upload, preserve);
    const second = new InterviewBlockQueue(async (item) => receipt(item.id), preserve);
    const one = first.enqueue(block('one'));
    expect(first.enqueue(block('one'))).toBe(one);
    await second.enqueue(block('other'));
    expect(preserve).toHaveBeenCalledTimes(1);
    finish();
    await one;
    expect(upload).toHaveBeenCalledTimes(1);
    expect(preserve).toHaveBeenCalledTimes(2);
  });

  it('serializes originals and never removes local data after a false acknowledgement', async () => {
    const preserve = vi.fn();
    const queue = new InterviewBlockQueue(async (item) => ({...receipt(item.id), preserved: false}), preserve);
    await expect(queue.enqueue(block('one'))).rejects.toThrow('Invalid block preservation receipt');
    await expect(queue.drain()).rejects.toThrow('Invalid block preservation receipt');
    expect(preserve).not.toHaveBeenCalled();
  });
});
