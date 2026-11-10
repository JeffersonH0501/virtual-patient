let worker: Worker | undefined;
let sequence = 0;
const pending = new Map<number, {resolve: () => void; reject: (error: Error) => void}>();

/** Older WebKit exposes durable OPFS writes through dedicated workers only. */
export const writeBlockFragment = async (file: FileSystemFileHandle, chunk: Blob): Promise<void> => {
  if (typeof file.createWritable === 'function') {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([(async () => {
        const writer = await file.createWritable();
        try {
          await writer.write(chunk); await writer.close();
        } catch (error) {
          void writer.abort().catch(() => undefined); throw error;
        }
      })(), new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('Local block write timed out')), 10_000);
      })]);
    } finally {
      clearTimeout(timer);
    }
    return;
  }
  if (!worker) {
    worker = new Worker(new URL('./blockStorage.worker.ts', import.meta.url), {type: 'module'});
    worker.onmessage = (event: MessageEvent<{id: number; ok: boolean}>) => {
      const request = pending.get(event.data.id);
      pending.delete(event.data.id);
      if (event.data.ok) request?.resolve();
      else request?.reject(new Error('Local block storage could not confirm the fragment'));
    };
    worker.onerror = () => {
      for (const request of pending.values()) request.reject(new Error('Local block storage worker failed'));
      pending.clear(); worker?.terminate(); worker = undefined;
    };
  }
  const data = await chunk.arrayBuffer();
  await new Promise<void>((resolve, reject) => {
    const id = sequence++;
    const timer = setTimeout(() => {
      pending.delete(id); reject(new Error('Local block write timed out'));
    }, 10_000);
    pending.set(id, {resolve: () => {
      clearTimeout(timer); resolve();
    }, reject: (error) => {
      clearTimeout(timer); reject(error);
    }});
    worker!.postMessage({id, file, data}, [data]);
  });
};
