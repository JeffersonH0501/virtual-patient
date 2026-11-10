type SyncFile = {write(data: ArrayBuffer, options: {at: number}): number; truncate(size: number): void;
  flush(): void | Promise<void>; close(): void | Promise<void>};

self.addEventListener('message', async (event: MessageEvent<{id: number; file: FileSystemFileHandle; data: ArrayBuffer}>) => {
  const {id, file, data} = event.data;
  let access: SyncFile | undefined;
  try {
    access = await (file as FileSystemFileHandle & {createSyncAccessHandle(): Promise<SyncFile>}).createSyncAccessHandle();
    if (access.write(data, {at: 0}) !== data.byteLength) throw new Error('Local block write was incomplete');
    access.truncate(data.byteLength);
    await access.flush();
    await access.close();
    access = undefined;
    self.postMessage({id, ok: true});
  } catch {
    self.postMessage({id, ok: false});
  } finally {
    await access?.close();
  }
});
