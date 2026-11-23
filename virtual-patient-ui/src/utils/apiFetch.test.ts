import {afterEach, expect, it, vi} from 'vitest';
import {apiFetch} from './apiFetch';
import {setSessionResponseOwner} from './sessionResponses';

afterEach(() => {
  setSessionResponseOwner(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('bounds shared review reads independently of a caller and allows retry after timeout', async () => {
  setSessionResponseOwner('student:1');
  const deadline = new AbortController();
  const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(deadline.signal);
  const fetch = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init.signal?.addEventListener('abort', () => reject(init.signal?.reason), {once: true});
  }));
  vi.stubGlobal('fetch', fetch);
  const caller = new AbortController();
  const pending = apiFetch('/medical-interviews/7/complete', {signal: caller.signal});
  const failure = expect(pending).rejects.toHaveProperty('name', 'TimeoutError');
  deadline.abort(new DOMException('Synthetic read deadline', 'TimeoutError'));
  await failure;
  expect(timeout).toHaveBeenCalledWith(30_000);
  fetch.mockResolvedValueOnce(new Response(JSON.stringify({status: 'completed'})));
  await expect(apiFetch('/medical-interviews/7/complete')).resolves.toHaveProperty('ok', true);
  expect(fetch).toHaveBeenCalledTimes(2);
});
