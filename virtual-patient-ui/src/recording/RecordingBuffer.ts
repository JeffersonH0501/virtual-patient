/* eslint-disable max-classes-per-file */

type DirectoryHandle = {
  getDirectoryHandle(name: string, options: {create: boolean}): Promise<DirectoryHandle>;
  getFileHandle(name: string, options: {create: boolean}): Promise<{
    createWritable(): Promise<{
      write(data: Blob): Promise<void>;
      close(): Promise<void>;
      abort(): Promise<void>;
    }>;
    getFile(): Promise<File>;
  }>;
  removeEntry(name: string): Promise<void>;
};

type StorageWithDirectory = StorageManager & {
  getDirectory?: () => Promise<DirectoryHandle>;
};

export interface RecordingBuffer {
  append(chunk: Blob): Promise<void>;
  finish(filename: string, contentType: string): Promise<File>;
  discard(): Promise<void>;
}

class MemoryRecordingBuffer implements RecordingBuffer {
  private chunks: Blob[] = [];

  async append(chunk: Blob): Promise<void> {
    this.chunks.push(chunk);
  }

  async finish(filename: string, contentType: string): Promise<File> {
    return new File(this.chunks, filename, {type: contentType});
  }

  async discard(): Promise<void> {
    this.chunks = [];
  }
}

class OpfsRecordingBuffer implements RecordingBuffer {
  private queue = Promise.resolve();

  private constructor(
    private readonly directory: DirectoryHandle,
    private readonly temporaryName: string,
    private readonly writer: {
      write(data: Blob): Promise<void>;
      close(): Promise<void>;
      abort(): Promise<void>;
    },
    private readonly fileHandle: {getFile(): Promise<File>},
  ) {}

  static async create(key: string): Promise<OpfsRecordingBuffer | null> {
    const storage = navigator.storage as StorageWithDirectory;
    if (!storage.getDirectory) return null;
    const root = await storage.getDirectory();
    const directory = await root.getDirectoryHandle('virtual-patient-recordings', {create: true});
    const temporaryName = `${key}-${crypto.randomUUID()}.part`;
    const fileHandle = await directory.getFileHandle(temporaryName, {create: true});
    const writer = await fileHandle.createWritable();
    return new OpfsRecordingBuffer(directory, temporaryName, writer, fileHandle);
  }

  async append(chunk: Blob): Promise<void> {
    this.queue = this.queue.then(() => this.writer.write(chunk));
    await this.queue;
  }

  async finish(filename: string, contentType: string): Promise<File> {
    await this.queue;
    await this.writer.close();
    const file = await this.fileHandle.getFile();
    return new File([file], filename, {type: contentType});
  }

  async discard(): Promise<void> {
    try {
 await this.writer.abort();
} catch { /* The writer may already be closed. */ }
    try {
 await this.directory.removeEntry(this.temporaryName);
} catch { /* Already removed. */ }
  }
}

export const createRecordingBuffer = async (key: string): Promise<RecordingBuffer> => {
  try {
    return await OpfsRecordingBuffer.create(key) ?? new MemoryRecordingBuffer();
  } catch {
    return new MemoryRecordingBuffer();
  }
};
