import {afterEach, expect, it, vi} from 'vitest';
import {writeBlockFragment} from './writeBlockFragment';

afterEach(() => vi.unstubAllGlobals());

it('confirms a modern OPFS fragment only after its writer closes', async () => {
  let closed = false;
  const writer = {write: vi.fn(), close: vi.fn(async () => {
    closed = true;
  }), abort: vi.fn()};
  await writeBlockFragment({createWritable: async () => writer} as unknown as FileSystemFileHandle, new Blob(['original']));
  expect(closed).toBe(true);
  expect(writer.abort).not.toHaveBeenCalled();
});

it('uses the worker acknowledgement when createWritable is unavailable', async () => {
  const sent = vi.fn(function (this: {onmessage: (event: {data: {id: number; ok: boolean}}) => void}, payload: {id: number}) {
    queueMicrotask(() => this.onmessage({data: {id: payload.id, ok: true}}));
  });
  vi.stubGlobal('Worker', vi.fn(function () {
    return {postMessage: sent};
  }));
  await writeBlockFragment({} as FileSystemFileHandle, {arrayBuffer: async () => new ArrayBuffer(2)} as Blob);
  expect(sent).toHaveBeenCalledTimes(1);
});
