import {getAuthHeaders} from '../auth/authHeaders';
import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';

type TranscriptionResponse = {
  text: string;
  language?: string | null;
  provider: string;
  model: string;
};

const ATTEMPTS = 2;
const ATTEMPT_TIMEOUT_MS = 20_000;

export const transcribeStudentAudio = async (
  audio: Blob,
  filename: string,
  language?: 'en' | 'es',
  interviewId?: number,
): Promise<TranscriptionResponse> => {
  const form = new FormData();
  form.append('audio', audio, filename);
  if (language) form.append('language', language);
  if (interviewId) form.append('interview_id', String(interviewId));
  // A request that never reaches the server must not hold the turn: bound each attempt and retry once.
  for (let attempt = 1; ; attempt++) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS);
    try {
      const response = await apiFetch(`${API_URL}/speech/transcriptions`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: form,
        signal: controller.signal,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw Object.assign(new Error(body.detail || 'Server speech transcription failed'), {status: response.status});
      }
      return await response.json() as TranscriptionResponse;
    } catch (error) {
      const transient = error instanceof TypeError || (error instanceof DOMException && error.name === 'AbortError') ||
        (error instanceof Error && 'status' in error && [502, 503, 504].includes(Number(error.status)));
      if (!transient || attempt >= ATTEMPTS) throw error;
      console.warn('Speech transcription attempt failed; retrying', {attempt, error: error instanceof Error ? error.name : 'unknown'});
    } finally {
      window.clearTimeout(timeout);
    }
  }
};
