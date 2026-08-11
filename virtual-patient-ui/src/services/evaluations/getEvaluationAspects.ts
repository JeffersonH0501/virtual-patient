import { transformToCamelCase } from '../../utils/apiTransform';
import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';

export type EvaluationAspectsResponse = {
  aspects: {
    generalCommunication: string[];
    showInterest: string[];
    showEmpathy: string[];
    speakClearly: string[];
    openCommunication: string[];
    completeness: string[];
  };
};

export const getEvaluationAspects = async (): Promise<EvaluationAspectsResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/evaluations/aspects`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch evaluation aspects');
  }

  const data = await response.json();
  return transformToCamelCase(data) as EvaluationAspectsResponse;
};
