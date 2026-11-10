import { getAuthHeaders } from '../auth/authHeaders';
import { CreateHypothesisRequest, UserHypothesis } from '../../types/hypothesis';
import {blockFetch} from '../recordings/blocks';

type Response = UserHypothesis[];

export const createHypothesis = async (
  interviewId: string,
  hypotheses: CreateHypothesisRequest,
  captureSegmentId?: string | null,
): Promise<UserHypothesis[]> => {
  const authHeaders = getAuthHeaders();
  const init: RequestInit = {
    method: 'POST',
    body: JSON.stringify(hypotheses.map((hypothesis) => ({
      hypothesis_text: hypothesis.hypothesisText,
      hypothesis_order: hypothesis.hypothesisOrder,
    }))),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
      ...(captureSegmentId ? {'X-Capture-Segment': captureSegmentId} : {}),
    },
  };
  const response = await blockFetch(Number(interviewId), '/hypotheses', init);

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = (await response.json()) as Response;

  return data;
};
