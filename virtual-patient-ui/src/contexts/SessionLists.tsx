import {PropsWithChildren, useEffect, useMemo, useRef} from 'react';
import {User} from '../types/user';
import {getInterview} from '../services/interviews/getInterview';
import {getInterviewRecap} from '../services/recordings';
import {setSessionResponseOwner} from '../utils/sessionResponses';
import {apiFetch} from '../utils/apiFetch';
import {API_URL} from '../utils/request';
import {getAuthHeaders} from '../services/auth/authHeaders';
import {createLists, SessionListsContext} from './sessionListsStore';

export function SessionListsProvider({user, interviewFlow, children}: PropsWithChildren<{user?: User | null; interviewFlow: boolean}>) {
  const id = user?.id;
  const role = user?.role;

  const lists = useMemo(() => createLists(), [id, role]);
  const wasInInterview = useRef(false);
  useEffect(() => {
    setSessionResponseOwner(id == null ? null : `${id}:${role}`);
    return () => setSessionResponseOwner(null);
  }, [id, role]);
  useEffect(() => {
    if (id == null) return;
    const refresh = wasInInterview.current && !interviewFlow;
    wasInInterview.current = interviewFlow;
    void lists.cases.load();
    void lists.personalities.load();
    if (role === 'admin') {
      void lists.users.load();
      void lists.adminHistory.load(refresh);
    } else {
      void lists.interviews.load(refresh);
    }
    let cancelled = false;
    if (!interviewFlow) {
      const history = role === 'admin' ? lists.adminHistory : lists.interviews;
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
            if (detail.reviewAccess?.canViewAssessments !== false) paths.push('doctor-ratings', 'learning-moments');
            if (role !== 'student' && detail.reviewAccess?.canViewAssessments !== false) paths.push('reviewers');
            for (const path of paths) {
              if (cancelled) return;
              const response = await apiFetch(`${API_URL}/medical-interviews/${item.id}/${path}`, {headers: getAuthHeaders()});
              if (!response.ok) break;
            }
            if (!cancelled && role === 'doctor' && detail.reviewAccess?.assignmentId != null) {
              await apiFetch(`${API_URL}/doctor-assignments/${detail.reviewAccess.assignmentId}`, {headers: getAuthHeaders()});
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
  }, [id, interviewFlow, lists, role, user?.preferredLanguage]);
  return <SessionListsContext.Provider value={lists}>{children}</SessionListsContext.Provider>;
}

