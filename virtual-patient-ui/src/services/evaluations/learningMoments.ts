import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {LearningMomentsState} from '../../types/learningMoments';

export async function requestLearningMoments(interviewId: number, regenerate = false): Promise<LearningMomentsState> {
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}/learning-moments${regenerate ? '/regenerate' : ''}`, {
    method: regenerate ? 'POST' : 'GET', headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error('Learning moments request failed');
  return transformToCamelCase(await response.json()) as LearningMomentsState;
}
