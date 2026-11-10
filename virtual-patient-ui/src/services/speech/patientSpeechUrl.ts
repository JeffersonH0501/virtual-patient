import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export const patientSpeechUrl = (
  interviewId: number,
  messageId: number,
): string => `${API_URL}/medical-interviews/${interviewId}/messages/${messageId}/speech`;

export const loadPatientSpeechBlob = async (interviewId: number, messageId: number, signal: AbortSignal) => {
  const response = await fetch(patientSpeechUrl(interviewId, messageId), {
    headers: getAuthHeaders(), credentials: 'include', signal,
  });
  if (!response.ok) throw new Error('Patient speech request failed');
  const audio = await response.blob();
  if (!audio.size || !audio.type.startsWith('audio/')) throw new Error('Patient speech response contains no audio');
  return URL.createObjectURL(audio);
};
