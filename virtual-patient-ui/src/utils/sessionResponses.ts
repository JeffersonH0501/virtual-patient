let owner: string | null = null;
const responses = new Map<string, Promise<Response>>();

export const setSessionResponseOwner = (next: string | null) => {
  if (owner !== next) responses.clear();
  owner = next;
};
export const clearSessionResponses = () => responses.clear();

/** Cache authorized review JSON, never active capture state or media. */
export const sessionResponse = async (url: string, options: RequestInit, read: (shared?: boolean) => Promise<Response>): Promise<Response> => {
  const method = options.method?.toUpperCase() ?? 'GET';
  const eligible = owner && method === 'GET' && (/\/medical-interviews\/\d+\/(complete|recap|teacher-ratings|reviewers|self-rating|learning-moments)(?:\?|$)/.test(url) ||
    /\/teacher-assignments\/\d+(?:\?|$)/.test(url));
  if (!eligible) {
    const response = await read();
    if (response.ok && method !== 'GET') responses.clear();
    return response;
  }
  const key = `${owner}:${new Headers(options.headers).get('Authorization')}:${url}`;
  let pending = responses.get(key);
  if (!pending) {
    pending = read(true).then(async (response) => {
      const body = response.ok ? await response.clone().json() : null;
      const active = body && ((body.status && /\/complete(?:\?|$)/.test(url) && body.status !== 'completed') ||
        ['queued', 'processing'].includes(body.status) ||
        ['recording', 'paused', 'finalizing'].includes(body.recording_status) ||
        ['queued', 'processing'].includes(body.observation_processing?.status) ||
        ['queued', 'processing'].includes(body.evaluation_processing?.status));
      if ((!response.ok || active) && responses.get(key) === pending) responses.delete(key);
      return response;
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
