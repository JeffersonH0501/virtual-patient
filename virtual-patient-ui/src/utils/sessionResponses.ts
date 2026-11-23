let owner: string | null = null;
const responses = new Map<string, Promise<Response>>();

export const setSessionResponseOwner = (next: string | null) => {
  if (owner !== next) responses.clear();
  owner = next;
};

/** Cache authorized review JSON, never active capture state or media. */
export const sessionResponse = async (url: string, options: RequestInit, read: (shared?: boolean) => Promise<Response>): Promise<Response> => {
  const method = options.method?.toUpperCase() ?? 'GET';
  const eligible = owner && method === 'GET' && (/\/medical-interviews\/\d+\/(complete|recap|doctor-ratings|reviewers|self-rating|learning-moments)(?:\?|$)/.test(url) ||
    /\/doctor-assignments\/\d+(?:\?|$)/.test(url));
  if (!eligible) {
    const response = await read();
    if (response.ok && method !== 'GET') responses.clear();
    return response;
  }
  const key = `${owner}:${new Headers(options.headers).get('Authorization')}:${url}`;
  let pending = responses.get(key);
  if (!pending) {
    pending = read(true).then(async (response) => {
      // Cached data must outlive the fetch signal: its deadline may fire after this read completed.
      const payload = await response.text();
      const body = response.ok && payload ? JSON.parse(payload) : null;
      const active = body && ((body.status && /\/complete(?:\?|$)/.test(url) && body.status !== 'completed') ||
        ['queued', 'processing'].includes(body.status) ||
        ['recording', 'paused', 'finalizing'].includes(body.recording_status) ||
        ['queued', 'processing'].includes(body.observation_processing?.status) ||
        ['queued', 'processing'].includes(body.evaluation_processing?.status) ||
        ['queued', 'processing'].includes(body.replay?.status));
      if ((!response.ok || active) && responses.get(key) === pending) responses.delete(key);
      return new Response([204, 205, 304].includes(response.status) ? null : payload, {
        status: response.status, statusText: response.statusText, headers: response.headers,
      });
    }).catch((error) => {
      if (responses.get(key) === pending) responses.delete(key);
      throw error;
    });
    responses.set(key, pending);
  }
  const response = await pending;
  if (options.signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
  return response.clone();
};
