import {writeBlockFragment} from './writeBlockFragment';

export type BlockWindow = {start_ms: number; end_ms: number};
export type BlockMetadata = {
  capture_attempt_id: string;
  order: number;
  duration_ms: number;
  student_message_id: number | null;
  patient_message_id: number;
  student_speech: BlockWindow | null;
  student_speech_complete?: boolean;
  patient_playback: BlockWindow | null;
  patient_audio_missing: boolean;
  recovery: boolean;
  patient_playback_complete?: boolean;
  patient_roi_snapshots?: Record<string, number>[];
  interaction_area_snapshots?: Record<string, number>[];
};
export type LocalInterviewBlock = {
  id: string;
  scope: string;
  requestId: string;
  pendingContent?: string;
  mimeType: string;
  chunks: number;
  confirmedEndMs: number;
  expiresAt: string;
  metadata: Partial<BlockMetadata>;
  state: 'capturing' | 'closed' | 'preserved';
};

const openDatabase = (): Promise<IDBDatabase> => new Promise((resolve, reject) => {
  const request = indexedDB.open('virtual-patient-blocks', 1);
  request.onupgradeneeded = () => request.result.createObjectStore('blocks', {keyPath: 'id'}).createIndex('scope', 'scope');
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
  request.onblocked = () => reject(new Error('Local block storage is blocked'));
});

/** Metadata transactions finish only after the corresponding OPFS writer closes. */
export class InterviewBlockStore {
  constructor(readonly scope: string) {}

  private async transaction<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    const db = await openDatabase();
    try {
      return await new Promise<T>((resolve, reject) => {
        const transaction = db.transaction('blocks', mode);
        const request = operation(transaction.objectStore('blocks'));
        transaction.oncomplete = () => resolve(request.result);
        transaction.onabort = () => reject(transaction.error ?? new Error('Local block transaction aborted'));
        transaction.onerror = () => reject(transaction.error);
      });
    } finally {
      db.close();
    }
  }

  private async directory(blockId: string, create = false) {
    const root = await navigator.storage.getDirectory();
    const blocks = await root.getDirectoryHandle('virtual-patient-blocks', {create});
    const scope = await blocks.getDirectoryHandle(encodeURIComponent(this.scope), {create});
    return scope.getDirectoryHandle(blockId, {create});
  }

  async list(): Promise<LocalInterviewBlock[]> {
    const blocks = await this.transaction('readonly', (store) => store.index('scope').getAll(this.scope)) as LocalInterviewBlock[];
    return blocks.sort((a, b) => (a.metadata.order ?? 0) - (b.metadata.order ?? 0));
  }

  async put(block: LocalInterviewBlock): Promise<void> {
    if (block.scope !== this.scope) throw new Error('Block belongs to another capture account');
    await this.transaction('readwrite', (store) => store.put(block));
  }

  async patch(id: string, patch: Partial<LocalInterviewBlock>): Promise<LocalInterviewBlock> {
    const db = await openDatabase();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction('blocks', 'readwrite');
        const store = transaction.objectStore('blocks');
        const request = store.get(id);
        let next: LocalInterviewBlock;
        request.onsuccess = () => {
          const current = request.result as LocalInterviewBlock | undefined;
          if (!current || current.scope !== this.scope || (current.state !== 'capturing' && patch.state !== 'preserved')) {
            transaction.abort();
            return;
          }
          next = {...current, ...patch, metadata: {...current.metadata, ...patch.metadata},
            chunks: Math.max(current.chunks, patch.chunks ?? 0), confirmedEndMs: Math.max(current.confirmedEndMs, patch.confirmedEndMs ?? 0)};
          store.put(next);
        };
        transaction.oncomplete = () => resolve(next);
        transaction.onabort = () => reject(transaction.error ?? new Error('Local block update was rejected'));
        transaction.onerror = () => reject(transaction.error);
      });
    } finally {
      db.close();
    }
  }

  async create(block: LocalInterviewBlock): Promise<void> {
    await this.directory(block.id, true);
    await this.transaction('readwrite', (store) => store.add(block));
  }

  async append(block: LocalInterviewBlock, chunk: Blob, endMs: number): Promise<void> {
    if (block.state !== 'capturing') throw new Error('A closed block is immutable');
    const directory = await this.directory(block.id);
    const handle = await directory.getFileHandle(String(block.chunks), {create: true});
    await writeBlockFragment(handle, chunk);
    const next = {...block, chunks: block.chunks + 1, confirmedEndMs: endMs};
    Object.assign(block, await this.patch(block.id, {chunks: next.chunks, confirmedEndMs: endMs}));
  }

  async original(block: LocalInterviewBlock, recoverMissing = false): Promise<File> {
    if (block.scope !== this.scope) throw new Error('Block belongs to another capture account');
    const directory = await this.directory(block.id);
    const chunks: File[] = [];
    for (let index = 0; index < block.chunks; index++) {
      try {
        const file = await (await directory.getFileHandle(String(index))).getFile();
        if (!file.size) {
          if (recoverMissing) continue;
          throw new Error('A confirmed local fragment is missing');
        }
        chunks.push(file);
      } catch (error) {
        if (!(recoverMissing && error instanceof DOMException && error.name === 'NotFoundError')) throw error;
      }
    }
    if (!chunks.length) throw new Error('No confirmed block fragments are available');
    return new File(chunks, block.id + (block.mimeType.includes('mp4') ? '.mp4' : '.webm'), {type: block.mimeType});
  }

  async removePreserved(block: LocalInterviewBlock): Promise<void> {
    if (block.state !== 'preserved') throw new Error('Unpreserved blocks cannot be removed');
    await this.erase(block);
  }

  async discardUnsent(block: LocalInterviewBlock): Promise<void> {
    const current = (await this.list()).find((item) => item.id === block.id);
    if (!current || current.state !== 'capturing' || current.pendingContent || current.metadata.student_message_id || current.metadata.patient_message_id) {
      throw new Error('Only an unsent intervention can be discarded');
    }
    await this.erase(current);
  }

  private async erase(block: LocalInterviewBlock): Promise<void> {
    try {
      const root = await navigator.storage.getDirectory();
      const blocks = await root.getDirectoryHandle('virtual-patient-blocks');
      const scope = await blocks.getDirectoryHandle(encodeURIComponent(this.scope));
      await scope.removeEntry(block.id, {recursive: true});
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'NotFoundError')) throw error;
    }
    await this.transaction('readwrite', (store) => store.delete(block.id));
  }

  async purgeExpired(): Promise<void> {
    for (const block of await this.list()) {
      if (Date.parse(block.expiresAt) <= Date.now()) await this.erase(block);
    }
  }
}
