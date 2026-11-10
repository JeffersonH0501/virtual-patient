const pending = new Map<string, Promise<void>>();

/** Serialize writes sharing an interview's server transaction boundary. */
export const captureFetch = (interviewId: string | number, url: string, init: RequestInit): Promise<Response> => {
  const key = String(interviewId);
  const request = (pending.get(key) ?? Promise.resolve()).then(() => fetch(url, {
    ...init, signal: init.signal ?? AbortSignal.timeout(60_000),
  }));
  const settled = request.then(() => undefined, () => undefined);
  pending.set(key, settled);
  void settled.then(() => {
    if (pending.get(key) === settled) pending.delete(key);
  });
  return request;
};
