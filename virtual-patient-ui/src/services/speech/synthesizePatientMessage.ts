import {getAuthHeaders} from '../auth/authHeaders';
import {API_URL} from '../../utils/request';

export const synthesizePatientMessage = async (
  interviewId: number,
  messageId: number,
): Promise<Blob> => {
  const response = await fetch(
    `${API_URL}/medical-interviews/${interviewId}/messages/${messageId}/speech`,
    {
      method: 'POST',
      headers: {
        accept: 'audio/mpeg',
        ...getAuthHeaders(),
      },
    },
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const detail =
      errorData && typeof errorData.detail === 'string'
        ? errorData.detail
        : 'Failed to synthesize patient speech';
    throw new Error(detail);
  }
  return response.blob();
};
