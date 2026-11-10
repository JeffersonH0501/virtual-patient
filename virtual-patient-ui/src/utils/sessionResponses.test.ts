import {afterEach, expect, it, vi} from 'vitest';
import {sessionResponse, setSessionResponseOwner} from './sessionResponses';

afterEach(() => setSessionResponseOwner(null));
const url = '/medical-interviews/12/complete?language=es';

it('deduplicates authorized reads and keeps cached response bodies reusable', async () => {
  setSessionResponseOwner('student:1');
  const read = vi.fn(async () => new Response(JSON.stringify({status: 'completed', messages: []})));
  const [first, second] = await Promise.all([sessionResponse(url, {}, read), sessionResponse(url, {}, read)]);
  expect(await first.json()).toEqual(await second.json());
  expect(await (await sessionResponse(url, {}, read)).json()).toHaveProperty('messages');
  expect(read).toHaveBeenCalledOnce();
});

it('clears account data and invalidates cached details after a successful mutation', async () => {
  setSessionResponseOwner('student:1');
  const read = vi.fn(async () => new Response(JSON.stringify({status: 'completed'})));
  await sessionResponse(url, {}, read);
  await sessionResponse('/self-rating', {method: 'POST'}, async () => new Response('{}'));
  await sessionResponse(url, {}, read);
  setSessionResponseOwner('student:2');
  await sessionResponse(url, {}, read);
  expect(read).toHaveBeenCalledTimes(3);
});

it('does not freeze active interviews or cache playback media', async () => {
  setSessionResponseOwner('student:1');
  const read = vi.fn(async () => new Response(JSON.stringify({status: 'processing'})));
  await sessionResponse(url, {}, read);
  await sessionResponse(url, {}, read);
  await sessionResponse('/medical-interviews/12/recording/assets/student_video', {}, read);
  await sessionResponse('/medical-interviews/12/recording/assets/student_video', {}, read);
  await sessionResponse('/medical-interviews/12/learning-moments', {}, read);
  await sessionResponse('/medical-interviews/12/learning-moments', {}, read);
  expect(read).toHaveBeenCalledTimes(6);
});

it('keeps a shared preload usable when one view aborts its own read', async () => {
  setSessionResponseOwner('student:1');
  const controller = new AbortController();
  const read = vi.fn(async () => new Response(JSON.stringify({status: 'completed'})));
  controller.abort();
  const abandoned = sessionResponse(url, {signal: controller.signal}, read);
  const current = sessionResponse(url, {}, read);
  await expect(abandoned).rejects.toHaveProperty('name', 'AbortError');
  expect(await (await current).json()).toEqual({status: 'completed'});
  expect(read).toHaveBeenCalledOnce();
});
