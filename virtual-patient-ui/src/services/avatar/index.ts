import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';

export type AvatarSession = {
  provider: string;
  conversationId: string;
  conversationUrl: string;
  meetingToken: string | null;
};

export const startAvatarSession = async (
  interviewId: number,
): Promise<AvatarSession> => {
  const response = await fetch(
    `${API_URL}/medical-interviews/${interviewId}/avatar/session`,
    {method: 'POST', headers: getAuthHeaders()},
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Avatar session could not be started');
  }
  return transformToCamelCase(await response.json()) as AvatarSession;
};

export const endAvatarSession = async (
  interviewId: number,
  keepalive = false,
): Promise<void> => {
  await fetch(`${API_URL}/medical-interviews/${interviewId}/avatar/session`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
    keepalive,
  }).catch(() => undefined);
};
