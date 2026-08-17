import {Message, SendMessageResponse} from '../../types';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export const sendMessage = async (
  interviewId: string,
  message: string,
): Promise<SendMessageResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/messages`, {
    method: 'POST',
    body: JSON.stringify({content: message}),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  const data: unknown = await response.json();
  if (!response.ok) {
    const detail =
      data &&
      typeof data === 'object' &&
      'detail' in data &&
      typeof data.detail === 'string'
        ? data.detail
        : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  if (
    !data ||
    typeof data !== 'object' ||
    !('messages' in data) ||
    !Array.isArray(data.messages)
  ) {
    throw new Error('The message endpoint returned an invalid response');
  }

  const newMessageIds =
    'new_message_ids' in data && Array.isArray(data.new_message_ids)
      ? data.new_message_ids.filter((id): id is number => typeof id === 'number')
      : [];

  return {
    messages: transformToCamelCase(data.messages) as Message[],
    newMessageIds,
  };
};
