import {Message, SendMessageResponse} from '../../types';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {handleUnauthorized} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {captureFetch} from './captureFetch';
import type {StudentCaptureTiming} from '../../types/recording';
import {turnFetch} from '../recordings/turns';
import {InterviewTurnStore} from '../../recording/InterviewTurnStore';
import {CaptureSyncError} from '../../recording/CaptureSyncError';

const MESSAGE_TIMEOUT_MS = 120_000;

export const sendMessage = async (
  interviewId: string,
  message: string,
  clientRequestId?: string,
  segmentId?: string,
  captureTiming?: StudentCaptureTiming,
): Promise<SendMessageResponse> => {
  if (captureTiming?.turn_media_id && captureTiming.capture_scope && clientRequestId) {
    const store = new InterviewTurnStore(captureTiming.capture_scope);
    const turn = (await store.list()).find((item) => item.id === captureTiming.turn_media_id);
    if (!turn || turn.state !== 'capturing') throw new Error('The active local turn is unavailable');
    turn.requestId = clientRequestId;
    turn.pendingContent = message;
    await store.patch(turn.id, {requestId: clientRequestId, pendingContent: message});
  }
  const authHeaders = getAuthHeaders();
  const init: RequestInit = {
    method: 'POST',
    body: JSON.stringify({content: message, client_request_id: clientRequestId, segment_id: segmentId}),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  };
  const response = captureTiming?.turn_media_id
    // One deadline covers retries and offline waits; the pending request key survives for an explicit retry.
    ? await turnFetch(Number(interviewId), '/messages', {...init, signal: AbortSignal.timeout(MESSAGE_TIMEOUT_MS)}, captureTiming.capture_scope)
    : await captureFetch(interviewId, `${API_URL}/medical-interviews/${interviewId}/messages`, init);

  // An expired session must recover centrally (clear token + redirect) instead
  // of dead-ending the student on a generic send error.
  if (response.status === 401) handleUnauthorized();

  const data: unknown = await response.json();
  if (!response.ok) {
    const detail =
      data &&
      typeof data === 'object' &&
      'detail' in data &&
      typeof data.detail === 'string'
        ? data.detail
        : `Request failed with status ${response.status}`;
    if (captureTiming?.turn_media_id) throw new CaptureSyncError(response.status, detail);
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

  if (captureTiming?.turn_media_id && captureTiming.capture_scope) {
    const store = new InterviewTurnStore(captureTiming.capture_scope);
    const turn = (await store.list()).find((item) => item.id === captureTiming.turn_media_id);
    if (!turn) throw new Error('The local turn was lost while delivering the response');
    const saved = transformToCamelCase(data.messages) as Message[];
    turn.metadata.message_id = saved.find((item) => newMessageIds.includes(item.id) && item.senderType === 'user')?.id;
    turn.pendingContent = undefined;
    await store.patch(turn.id, {pendingContent: undefined, metadata: {message_id: turn.metadata.message_id}});
  }

  return {
    messages: transformToCamelCase(data.messages) as Message[],
    newMessageIds,
  };
};
