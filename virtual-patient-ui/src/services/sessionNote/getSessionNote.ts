import { transformToCamelCase } from '../../utils/apiTransform';
import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { SessionNote } from '../../types/sessionNote';

export const getSessionNote = async (interviewId: string): Promise<SessionNote | null> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/session-notes`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch session note');
  }

  const data = await response.json();
  const notes = transformToCamelCase(data) as SessionNote[];
  
  // Return the first note or null if no notes exist
  return notes.length > 0 ? notes[0] : null;
};

