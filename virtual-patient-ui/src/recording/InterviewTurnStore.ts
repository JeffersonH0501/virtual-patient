import {writeTurnFragment} from './writeTurnFragment';

export type TurnCaptureMetadata = {
  capture_attempt_id: string;
  order: number;
  duration_ms: number;
  /** Null for an idle clip that keeps the replay continuous between turns. */
  message_id: number | null;
  speaker: 'student' | 'patient';
  session_clock_ms: number;
  /** Start of the analysed speech window inside a student clip. */
  speech_start_ms?: number | null;
  playback_start_ms?: number | null;
  playback_end_ms?: number | null;
  playback_complete?: boolean;
  interaction_area_snapshots?: Record<string, number>[];
};
export type LocalInterviewTurn = {
  id: string;
  scope: string;
  requestId: string;
  pendingContent?: string;
  mimeType: string;
  chunks: number;
  confirmedEndMs: number;
  expiresAt: string;
  metadata: Partial<TurnCaptureMetadata>;
  state: 'capturing' | 'closed' | 'preserved';
};

const openDatabase = (): Promise<IDBDatabase> => new Promise((resolve, reject) => {
  const request = indexedDB.open('virtual-patient-turns', 1);
  request.onupgradeneeded = () => request.result.createObjectStore('turns', {keyPath: 'id'}).createIndex('scope', 'scope');
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
  request.onblocked = () => reject(new Error('Local turn storage is blocked'));
});

/** Metadata transactions finish only after the corresponding OPFS writer closes. */
export class InterviewTurnStore {
  constructor(readonly scope: string) {}

  private async transaction<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    const db = await openDatabase();
    try {
      return await new Promise<T>((resolve, reject) => {
        const transaction = db.transaction('turns', mode);
        const request = operation(transaction.objectStore('turns'));
        transaction.oncomplete = () => resolve(request.result);
        transaction.onabort = () => reject(transaction.error ?? new Error('Local turn transaction aborted'));
        transaction.onerror = () => reject(transaction.error);
      });
    } finally {
      db.close();
    }
  }

  private async directory(turnId: string, create = false) {
    const root = await navigator.storage.getDirectory();
    const turns = await root.getDirectoryHandle('virtual-patient-turns', {create});
    const scope = await turns.getDirectoryHandle(encodeURIComponent(this.scope), {create});
    return scope.getDirectoryHandle(turnId, {create});
  }

  async list(): Promise<LocalInterviewTurn[]> {
    const turns = await this.transaction('readonly', (store) => store.index('scope').getAll(this.scope)) as LocalInterviewTurn[];
    return turns.sort((a, b) => (a.metadata.order ?? 0) - (b.metadata.order ?? 0));
  }

  async put(turn: LocalInterviewTurn): Promise<void> {
    if (turn.scope !== this.scope) throw new Error('Turn belongs to another capture account');
    await this.transaction('readwrite', (store) => store.put(turn));
  }

  async patch(id: string, patch: Partial<LocalInterviewTurn>): Promise<LocalInterviewTurn> {
    const db = await openDatabase();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction('turns', 'readwrite');
        const store = transaction.objectStore('turns');
        const request = store.get(id);
        let next: LocalInterviewTurn;
        request.onsuccess = () => {
          const current = request.result as LocalInterviewTurn | undefined;
          if (!current || current.scope !== this.scope || (current.state !== 'capturing' && patch.state !== 'preserved')) {
            transaction.abort();
            return;
          }
          next = {...current, ...patch, metadata: {...current.metadata, ...patch.metadata},
            chunks: Math.max(current.chunks, patch.chunks ?? 0), confirmedEndMs: Math.max(current.confirmedEndMs, patch.confirmedEndMs ?? 0)};
          store.put(next);
        };
        transaction.oncomplete = () => resolve(next);
        transaction.onabort = () => reject(transaction.error ?? new Error('Local turn update was rejected'));
        transaction.onerror = () => reject(transaction.error);
      });
    } finally {
      db.close();
    }
  }

  async create(turn: LocalInterviewTurn): Promise<void> {
    await this.directory(turn.id, true);
    await this.transaction('readwrite', (store) => store.add(turn));
  }

  async append(turn: LocalInterviewTurn, chunk: Blob, endMs: number): Promise<void> {
    if (turn.state !== 'capturing') throw new Error('A closed turn is immutable');
    const directory = await this.directory(turn.id);
    const handle = await directory.getFileHandle(String(turn.chunks), {create: true});
    await writeTurnFragment(handle, chunk);
    const next = {...turn, chunks: turn.chunks + 1, confirmedEndMs: endMs};
    Object.assign(turn, await this.patch(turn.id, {chunks: next.chunks, confirmedEndMs: endMs}));
  }

  async original(turn: LocalInterviewTurn, recoverMissing = false): Promise<File> {
    if (turn.scope !== this.scope) throw new Error('Turn belongs to another capture account');
    const directory = await this.directory(turn.id);
    const chunks: File[] = [];
    for (let index = 0; index < turn.chunks; index++) {
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
    if (!chunks.length) throw new Error('No confirmed turn fragments are available');
    return new File(chunks, turn.id + (turn.mimeType.includes('mp4') ? '.mp4' : '.webm'), {type: turn.mimeType});
  }

  async removePreserved(turn: LocalInterviewTurn): Promise<void> {
    if (turn.state !== 'preserved') throw new Error('Unpreserved turns cannot be removed');
    await this.erase(turn);
  }

  async discardUnsent(turn: LocalInterviewTurn): Promise<void> {
    const current = (await this.list()).find((item) => item.id === turn.id);
    if (!current || current.state !== 'capturing' || current.pendingContent || current.metadata.message_id) {
      throw new Error('Only an unsent intervention can be discarded');
    }
    await this.erase(current);
  }

  private async erase(turn: LocalInterviewTurn): Promise<void> {
    try {
      const root = await navigator.storage.getDirectory();
      const turns = await root.getDirectoryHandle('virtual-patient-turns');
      const scope = await turns.getDirectoryHandle(encodeURIComponent(this.scope));
      await scope.removeEntry(turn.id, {recursive: true});
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'NotFoundError')) throw error;
    }
    await this.transaction('readwrite', (store) => store.delete(turn.id));
  }

  async purgeExpired(): Promise<void> {
    for (const turn of await this.list()) {
      if (Date.parse(turn.expiresAt) <= Date.now()) await this.erase(turn);
    }
  }
}
