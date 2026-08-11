import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {Interview} from '../../types/interview';

type CreateInterviewPayload = {
  clinical_case_id: string;
  patient_name?: string;
  patient_photo?: string;
  patient_gender?: string;
  personality_id?: number;
};

type Response = {
  interview: Interview;
};

export const createInterview = async (payload: CreateInterviewPayload) => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews`, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const {interview} = (await response.json()) as Response;

  return interview;
};
