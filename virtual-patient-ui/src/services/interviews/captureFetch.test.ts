import {afterEach, expect, it, vi} from 'vitest';
import {captureFetch} from './captureFetch';

afterEach(() => vi.unstubAllGlobals());

it('orders fragment and turn writes without retrying either request', async () => {
  let complete!: (value: Response) => void;
  const request = vi.fn().mockReturnValueOnce(new Promise<Response>((resolve) => {
 complete = resolve;
}))
    .mockResolvedValue(new Response('{}'));
  vi.stubGlobal('fetch', request);
  const fragment = captureFetch(7, '/chunks/0', {method: 'POST'});
  const turn = captureFetch(7, '/turns/1', {method: 'PUT'});
  await Promise.resolve();
  expect(request).toHaveBeenCalledTimes(1);
  complete(new Response('{}'));
  await Promise.all([fragment, turn]);
  expect(request.mock.calls.map(([url]) => url)).toEqual(['/chunks/0', '/turns/1']);
});

it('releases the queue after a failed request and does not block other interviews', async () => {
  const request = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(new Response('{}'));
  vi.stubGlobal('fetch', request);
  await expect(captureFetch(7, '/failed', {})).rejects.toThrow('Offline');
  await Promise.all([captureFetch(7, '/next', {}), captureFetch(8, '/other', {})]);
  expect(request).toHaveBeenCalledTimes(3);
});
