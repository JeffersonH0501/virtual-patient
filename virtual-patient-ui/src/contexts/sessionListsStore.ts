import {createContext} from 'react';
import {getDefaultCases} from '../services/clinicalCases';
import {getPersonalities} from '../services/personalities';
import {getInterviews} from '../services/interviews/getInterviews';
import {getAdminInterviews} from '../services/interviews/getAdminInterviews';
import {listManagedUsers} from '../services/users/manageUsers';

const batchSize = 100;

async function collect<T>(read: (offset: number) => Promise<{items: T[]; total?: number}>) {
  const items: T[] = [];
  for (;;) {
    const page = await read(items.length);
    items.push(...page.items);
    if (!page.items.length || (page.total == null ? page.items.length < batchSize : items.length >= page.total)) {
      return items;
    }
  }
}

function createList<T>(fetchList: () => Promise<T[]>) {
  let snapshot: {items?: T[]; error?: string; loading: boolean} = {loading: true};
  let pending: Promise<void> | undefined;
  const listeners = new Set<() => void>();
  const publish = (next: typeof snapshot) => {
    snapshot = next;
    listeners.forEach((listener) => listener());
  };
  const load = (refresh = false) => {
    if (!refresh && (pending || snapshot.items)) return pending ?? Promise.resolve();
    const request = Promise.resolve().then(fetchList).then(
      (items) => {
        if (pending === request) publish({items, loading: false});
      },
      (error: unknown) => {
        if (pending === request) {
          publish({...snapshot, loading: false, error: error instanceof Error ? error.message : 'errors.generic'});
        }
      },
    ).finally(() => {
      if (pending === request) pending = undefined;
    });
    pending = request;
    publish({items: snapshot.items, loading: true});
    return request;
  };
  return {
    load,
    read: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export const createLists = () => ({
  personalities: createList(() => collect(async (offset) => ({
    items: await getPersonalities(offset, batchSize),
  }))),
  cases: createList(() => collect(async (offset) => ({
    items: await getDefaultCases(offset, batchSize),
  }))),
  interviews: createList(() => collect(async (offset) => ({items: await getInterviews(batchSize, offset)}))),
  users: createList(() => collect(async (offset) => {
    const {users, total} = await listManagedUsers(offset, batchSize);
    return {items: users, total};
  })),
  adminHistory: createList(() => collect(async (offset) => {
    const {interviews, total} = await getAdminInterviews(offset, batchSize);
    return {items: interviews, total};
  })),
});

export type Lists = ReturnType<typeof createLists>;
export const SessionListsContext = createContext<Lists | null>(null);

