import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export const patientSpeechUrl = (
  interviewId: number,
  messageId: number,
): string => `${API_URL}/medical-interviews/${interviewId}/messages/${messageId}/speech`;

const ATTEMPTS = 2;
const RESPONSE_TIMEOUT_MS = 8_000;

/** Wait for the response headers with a bound; a request the browser never sends must not hold the reply. */
const requestSpeech = async (url: string, signal: AbortSignal) => {
  for (let attempt = 1; ; attempt++) {
    const timeout = new AbortController();
    const timer = window.setTimeout(() => timeout.abort(), RESPONSE_TIMEOUT_MS);
    try {
      return await fetch(url, {headers: getAuthHeaders(), credentials: 'include', signal: AbortSignal.any([signal, timeout.signal])});
    } catch (error) {
      if (signal.aborted || attempt >= ATTEMPTS) throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }
};

export const loadPatientSpeechBlob = async (interviewId: number, messageId: number, signal: AbortSignal) => {
  const response = await requestSpeech(patientSpeechUrl(interviewId, messageId), signal);
  if (!response.ok) throw new Error('Patient speech request failed');
  const audio = await response.blob();
  if (!audio.size || !audio.type.startsWith('audio/')) throw new Error('Patient speech response contains no audio');
  return URL.createObjectURL(audio);
};
