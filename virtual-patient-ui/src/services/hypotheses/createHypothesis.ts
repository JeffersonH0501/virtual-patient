import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { CreateHypothesisRequest, UserHypothesis } from '../../types/hypothesis';

type Response = UserHypothesis[];

export const createHypothesis = async (
  interviewId: string,
  hypotheses: CreateHypothesisRequest
): Promise<UserHypothesis[]> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/hypotheses`, {
    method: 'POST',
    body: JSON.stringify(hypotheses.map(hypothesis => ({
      hypothesis_text: hypothesis.hypothesisText,
      hypothesis_order: hypothesis.hypothesisOrder,
    }))),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = (await response.json()) as Response;

  return data;
};
