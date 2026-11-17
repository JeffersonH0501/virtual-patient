import {describe, expect, it, vi} from 'vitest';
import {CaptureSyncError} from './CaptureSyncError';
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
    await expect(queue.drain()).resolves.toBeUndefined();
    expect(preserve).not.toHaveBeenCalled();
  });
  it('reports how many pending uploads have settled while draining, counting a failure as settled', async () => {
    const finish: Record<string, () => void> = {};
    const upload = vi.fn((item: LocalInterviewTurn) => new Promise<ReturnType<typeof receipt>>((resolve, reject) => {
      finish[item.id] = () => (item.id === 'bad' ? reject(new Error('upload failed')) : resolve(receipt(item.id)));
    }));
    const queue = new InterviewTurnQueue(upload, vi.fn());
    const uploads = [queue.enqueue(turn('one')), queue.enqueue(turn('bad')), queue.enqueue(turn('two'))];
    uploads.forEach((task) => task.catch(() => undefined));
    const seen: [number, number][] = [];
    const drained = queue.drain((settled, total) => seen.push([settled, total]));
    expect(seen).toEqual([[0, 3]]);
    // The queue uploads one original at a time: each starts only after the previous one settles.
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    finish.one();
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
    finish.bad();
    await vi.waitFor(() => expect(upload).toHaveBeenCalledTimes(3));
    finish.two();
    await drained;
    expect(seen).toEqual([[0, 3], [1, 3], [2, 3], [3, 3]]);
  });
  describe('retryTransient', () => {
    it('sends again an original that failed for a transient reason, once, and preserves it only on success', async () => {
      const preserve = vi.fn();
      const upload = vi.fn()
        .mockRejectedValueOnce(new CaptureSyncError(503, 'busy'))
        .mockImplementation(async (item: LocalInterviewTurn) => receipt(item.id));
      const queue = new InterviewTurnQueue(upload, preserve);
      await expect(queue.enqueue(turn('one'))).rejects.toThrow('busy');
      expect(preserve).not.toHaveBeenCalled();
      expect(queue.retryTransient()).toBe(1);
      await queue.drain();
      expect(upload).toHaveBeenCalledTimes(2);
      expect(preserve).toHaveBeenCalledOnce();
      // Nothing is left to retry, so a repeated reconnection cannot upload it a third time.
      expect(queue.retryTransient()).toBe(0);
      expect(upload).toHaveBeenCalledTimes(2);
    });

    it.each([
      ['a stale capture', new CaptureSyncError(409, 'stale_capture')],
      ['a content conflict', new CaptureSyncError(409, 'turn_media_conflict')],
      ['an invalid file', new CaptureSyncError(422, 'A video original is required')],
      ['an oversized original', new Error('turn-original-too-large')],
    ])('leaves %s failed: a retry cannot change the outcome', async (_name, error) => {
      const upload = vi.fn().mockRejectedValue(error);
      const queue = new InterviewTurnQueue(upload, vi.fn());
      await expect(queue.enqueue(turn('one'))).rejects.toThrow();
      expect(queue.retryTransient()).toBe(0);
      expect(upload).toHaveBeenCalledOnce();
    });

    it('does not start a second upload for an original that is still being sent slowly', async () => {
      let finish!: () => void;
      const upload = vi.fn((item: LocalInterviewTurn) => new Promise<ReturnType<typeof receipt>>((resolve) => {
        finish = () => resolve(receipt(item.id));
      }));
      const queue = new InterviewTurnQueue(upload, vi.fn());
      const sending = queue.enqueue(turn('slow'));
      expect(queue.retryTransient()).toBe(0);
      expect(queue.enqueue(turn('slow'))).toBe(sending);
      await vi.waitFor(() => expect(upload).toHaveBeenCalledOnce());
      finish();
      await sending;
      expect(upload).toHaveBeenCalledOnce();
    });
  });
  it('reports no work when nothing is pending', async () => {
    const seen: [number, number][] = [];
    await new InterviewTurnQueue(vi.fn(), vi.fn()).drain((settled, total) => seen.push([settled, total]));
    expect(seen).toEqual([[0, 0]]);
  });
});
