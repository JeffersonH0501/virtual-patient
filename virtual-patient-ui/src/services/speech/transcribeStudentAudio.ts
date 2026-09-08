import {getAuthHeaders} from '../auth/authHeaders';
import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';

type TranscriptionResponse = {
  text: string;
  language?: string | null;
  provider: string;
  model: string;
};

export const transcribeStudentAudio = async (
  audio: Blob,
  filename: string,
  language?: 'en' | 'es',
): Promise<TranscriptionResponse> => {
  const form = new FormData();
  form.append('audio', audio, filename);
  if (language) form.append('language', language);

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 45000);
  const response = await apiFetch(`${API_URL}/speech/transcriptions`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
    signal: controller.signal,
  }).finally(() => window.clearTimeout(timeout));
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Server speech transcription failed');
  }
  return response.json() as Promise<TranscriptionResponse>;
};
