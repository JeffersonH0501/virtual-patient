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

  const data = await response.json();
  return {
    messages: transformToCamelCase(data.messages) as Message[],
    newMessageIds: (data.new_message_ids || []) as number[],
  };
};
