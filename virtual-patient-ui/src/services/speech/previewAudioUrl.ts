const AUDIO_TYPE = 'audio/mpeg';

export const supportsProgressiveAudio = () =>
  typeof MediaSource !== 'undefined' && MediaSource.isTypeSupported(AUDIO_TYPE);

export const previewAudioUrl = async (response: Response, signal: AbortSignal, progressive: boolean) => {
  if (!progressive || !response.body) return URL.createObjectURL(await response.blob());

  const media = new MediaSource();
  const reader = response.body.getReader();
  const cancel = () => void reader.cancel().catch(() => undefined);
  signal.addEventListener('abort', cancel, {once: true});
  if (signal.aborted) cancel();

  media.addEventListener('sourceopen', async () => {
    try {
      if (signal.aborted) return;
      const buffer = media.addSourceBuffer(AUDIO_TYPE);
      while (!signal.aborted) {
        const chunk = await reader.read();
        if (signal.aborted) break;
        if (chunk.done) {
          media.endOfStream();
          break;
        }
        await new Promise<void>((resolve, reject) => {
          const listeners = new AbortController();
          const finish = (error?: Error) => {
            listeners.abort();
            signal.removeEventListener('abort', onAbort);
            if (error) reject(error);
            else resolve();
          };
          const onAbort = () => finish(new DOMException('Playback stopped', 'AbortError'));
          buffer.addEventListener('updateend', () => finish(), {once: true, signal: listeners.signal});
          buffer.addEventListener('error', () => finish(new Error('Audio buffer failed')), {once: true, signal: listeners.signal});
          signal.addEventListener('abort', onAbort, {once: true});
          try {
            buffer.appendBuffer(new Uint8Array(chunk.value));
          } catch (error) {
            finish(error instanceof Error ? error : new Error('Audio buffer failed'));
          }
        });
      }
    } catch {
      cancel();
      if (!signal.aborted && media.readyState === 'open') media.endOfStream('network');
    } finally {
      signal.removeEventListener('abort', cancel);
    }
  }, {once: true, signal});

  return URL.createObjectURL(media);
};
