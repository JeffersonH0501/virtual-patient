import {createContext, PropsWithChildren, useContext, useEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import {getDefaultCases} from '../services/clinicalCases';
import {getPersonalities} from '../services/personalities';
import {getInterviews} from '../services/interviews/getInterviews';
import {getOrganizationInterviews} from '../services/interviews/getOrganizationInterviews';
import {listManagedUsers} from '../services/users/manageUsers';
import {User} from '../types/user';
import {getInterview} from '../services/interviews/getInterview';
import {getInterviewRecap} from '../services/recordings';
import {setSessionResponseOwner} from '../utils/sessionResponses';
import {apiFetch} from '../utils/apiFetch';
import {API_URL} from '../utils/request';
import {getAuthHeaders} from '../services/auth/authHeaders';

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

const createLists = (organizationId?: number | null) => ({
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
  organization: createList(() => collect(async (offset) => {
    if (organizationId == null) throw new Error('errors.generic');
    const {interviews, total} = await getOrganizationInterviews(String(organizationId), offset, batchSize);
    return {items: interviews, total};
  })),
});

type Lists = ReturnType<typeof createLists>;
const SessionListsContext = createContext<Lists | null>(null);

export function SessionListsProvider({user, interviewFlow, children}: PropsWithChildren<{user?: User | null; interviewFlow: boolean}>) {
  const id = user?.id;
  const role = user?.role;
  const organizationId = user?.organizationId;
  const lists = useMemo(() => createLists(organizationId), [id, role, organizationId]);
  const wasInInterview = useRef(false);
  useEffect(() => {
    setSessionResponseOwner(id == null ? null : `${id}:${role}:${organizationId}`);
    return () => setSessionResponseOwner(null);
  }, [id, role, organizationId]);
  useEffect(() => {
    if (id == null) return;
    const refresh = wasInInterview.current && !interviewFlow;
    wasInInterview.current = interviewFlow;
    void lists.cases.load();
    void lists.personalities.load();
    if (role === 'superuser') {
      void lists.users.load();
      if (organizationId != null) void lists.organization.load(refresh);
    } else {
      void lists.interviews.load(refresh);
    }
    let cancelled = false;
    if (!interviewFlow) {
      const history = role === 'superuser' ? lists.organization : lists.interviews;
      void history.load().then(async () => {
        for (const item of history.read().items ?? []) {
          if (cancelled) return;
          try {
            const language = user?.preferredLanguage === 'es' ? 'es' : 'en';
            const detail = await getInterview(String(item.id), language);
            if (cancelled) return;
            if (detail.status !== 'completed') continue;
            await getInterviewRecap(item.id);
            if (cancelled) return;
            const paths: string[] = detail.userId === id ? ['self-rating'] : [];
            if (detail.reviewAccess?.canViewAssessments !== false) paths.push('teacher-ratings', 'learning-moments');
            if (role !== 'student' && detail.reviewAccess?.canViewAssessments !== false) paths.push('reviewers');
            for (const path of paths) {
              if (cancelled) return;
              const response = await apiFetch(`${API_URL}/medical-interviews/${item.id}/${path}`, {headers: getAuthHeaders()});
              if (!response.ok) break;
            }
            if (!cancelled && role === 'teacher' && detail.reviewAccess?.assignmentId != null) {
              await apiFetch(`${API_URL}/teacher-assignments/${detail.reviewAccess.assignmentId}`, {headers: getAuthHeaders()});
            }
          } catch {
            // Failed preloads remain available through the view's normal load/error handling.
          }
        }
      });
    }
    return () => {
      cancelled = true;
    };
  }, [id, interviewFlow, lists, organizationId, role, user?.preferredLanguage]);
  return <SessionListsContext.Provider value={lists}>{children}</SessionListsContext.Provider>;
}

export function useSessionList<Key extends keyof Lists>(key: Key, enabled = true, organizationId?: number | null) {
  const shared = useContext(SessionListsContext);
  const local = useMemo(() => createLists(organizationId), [organizationId]);
  const list = (shared ?? local)[key] as {
    load: Lists[Key]['load'];
    subscribe: Lists[Key]['subscribe'];
    read: () => ReturnType<Lists[Key]['read']>;
  };
  const snapshot = useSyncExternalStore(list.subscribe, list.read);
  useEffect(() => {
    if (enabled) void list.load();
  }, [enabled, list]);
  return {...snapshot, load: list.load};
}

