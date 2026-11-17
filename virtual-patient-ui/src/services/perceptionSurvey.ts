import {apiFetch} from '../utils/apiFetch';
import {API_URL} from '../utils/request';
import {getAuthHeaders} from './auth/authHeaders';

export type Survey = {eligible: boolean; status: 'DRAFT' | 'SUBMITTED'; answers: Record<string, number>; comments: Record<string, string>; sus_score: number | null; questionnaire_version: string | null; created_at: string | null; submitted_at: string | null; updated_at: string | null};

// Last loaded survey, shared so the header and the survey page reuse one fetch
// and the page opens instantly instead of showing a loading state again.
let cached: Survey | null = null;

/** The most recently loaded survey, or null before the first load. */
export const cachedSurvey = (): Survey | null => cached;

/** Clear the cache on sign-out so another account never sees a stale survey. */
export const clearSurveyCache = (): void => {
  cached = null;
};

export async function loadSurvey(): Promise<Survey> {
  const response = await apiFetch(`${API_URL}/perception-survey`, {headers: getAuthHeaders(), credentials: 'include'});
  if (!response.ok) throw new Error('Could not load survey');
  cached = await response.json() as Survey;
  return cached;
}

export async function saveSurvey(answers: Record<string, number>, comments: Record<string, string>, action: 'save' | 'submit'): Promise<Survey> {
  const response = await apiFetch(`${API_URL}/perception-survey`, {method: 'PUT', credentials: 'include',
    headers: {...getAuthHeaders(), 'Content-Type': 'application/json'}, body: JSON.stringify({answers, comments, action})});
  if (!response.ok) throw new Error('Could not save survey');
  const result = await response.json() as Survey;
  cached = result;
  window.dispatchEvent(new Event('perception-survey-updated'));
  return result;
}
