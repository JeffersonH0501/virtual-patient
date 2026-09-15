import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {Interview} from '../../types/interview';

type CreateInterviewPayload = {
  clinical_case_id: string;
  patient_response_language: 'en' | 'es';
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
    // Surface the backend detail (e.g. an already in-progress interview) so the
    // caller can show a meaningful message instead of a generic HTTP error.
    const errorBody = (await response.json().catch(() => null)) as {detail?: string} | null;
    const error = new Error(errorBody?.detail || `HTTP error! status: ${response.status}`);
    (error as Error & {status?: number}).status = response.status;
    throw error;
  }

  const {interview} = (await response.json()) as Response;

  return interview;
};
