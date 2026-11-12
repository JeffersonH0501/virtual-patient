import {describe, expect, it, vi} from 'vitest';
import {InterviewTurnQueue} from './InterviewTurnQueue';
import type {LocalInterviewTurn} from './InterviewTurnStore';

const turn = (id: string) => ({id, state: 'closed'} as LocalInterviewTurn);
const receipt = (id: string) => ({turn_media_id: id, preserved: true, sha256: 'a'.repeat(64), metadata_hash: 'b'.repeat(64)});

describe('InterviewTurnQueue', () => {
  it('deduplicates an original and keeps another interview independent of a slow upload', async () => {
    let finish!: () => void;
    const slow = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const preserve = vi.fn();
    const upload = vi.fn(async (item: LocalInterviewTurn) => {
      await slow; return receipt(item.id);
    });
    const first = new InterviewTurnQueue(upload, preserve);
    const second = new InterviewTurnQueue(async (item) => receipt(item.id), preserve);
    const one = first.enqueue(turn('one'));
    expect(first.enqueue(turn('one'))).toBe(one);
    await second.enqueue(turn('other'));
    expect(preserve).toHaveBeenCalledTimes(1);
    finish();
    await one;
    expect(upload).toHaveBeenCalledTimes(1);
    expect(preserve).toHaveBeenCalledTimes(2);
  });

  it('serializes originals and never removes local data after a false acknowledgement', async () => {
    const preserve = vi.fn();
    const queue = new InterviewTurnQueue(async (item) => ({...receipt(item.id), preserved: false}), preserve);
    await expect(queue.enqueue(turn('one'))).rejects.toThrow('Invalid turn preservation receipt');
    await expect(queue.drain()).rejects.toThrow('Invalid turn preservation receipt');
    expect(preserve).not.toHaveBeenCalled();
  });
});
