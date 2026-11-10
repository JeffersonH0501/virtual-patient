import {apiFetch} from '../utils/apiFetch';
import {API_URL} from '../utils/request';
import {getAuthHeaders} from './auth/authHeaders';

export type Survey = {eligible: boolean; status: 'DRAFT' | 'SUBMITTED'; answers: Record<string, number>; comments: Record<string, string>; cuq_score: number | null; created_at: string | null; submitted_at: string | null; updated_at: string | null};

export async function loadSurvey(): Promise<Survey> {
  const response = await apiFetch(`${API_URL}/perception-survey`, {headers: getAuthHeaders(), credentials: 'include'});
  if (!response.ok) throw new Error('Could not load survey');
  return response.json();
}

export async function saveSurvey(answers: Record<string, number>, comments: Record<string, string>, action: 'save' | 'submit'): Promise<Survey> {
  const response = await apiFetch(`${API_URL}/perception-survey`, {method: 'PUT', credentials: 'include',
    headers: {...getAuthHeaders(), 'Content-Type': 'application/json'}, body: JSON.stringify({answers, comments, action})});
  if (!response.ok) throw new Error('Could not save survey');
  const result = await response.json() as Survey;
  window.dispatchEvent(new Event('perception-survey-updated'));
  return result;
}
