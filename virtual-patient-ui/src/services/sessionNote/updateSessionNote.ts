import { transformToCamelCase, transformToSnakeCase } from '../../utils/apiTransform';
import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { CreateSessionNoteRequest, SessionNote } from '../../types/sessionNote';

export const updateSessionNote = async (
  interviewId: string,
  note: CreateSessionNoteRequest
): Promise<SessionNote> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/session-notes`, {
    method: 'POST',
    body: JSON.stringify([transformToSnakeCase(note)]),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to update session note');
  }

  const data = await response.json();
  const notes = transformToCamelCase(data) as SessionNote[];
  
  // Return the first note (there should only be one)
  return notes[0];
};

