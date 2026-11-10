import {Message, SendMessageResponse} from '../../types';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {captureFetch} from './captureFetch';
import type {StudentCaptureTiming} from '../../types/recording';
import {blockFetch} from '../recordings/blocks';
import {InterviewBlockStore} from '../../recording/InterviewBlockStore';
import {CaptureSyncError} from '../../recording/CaptureSyncError';

export const sendMessage = async (
  interviewId: string,
  message: string,
  clientRequestId?: string,
  segmentId?: string,
  captureTiming?: StudentCaptureTiming,
): Promise<SendMessageResponse> => {
  if (captureTiming?.block_id && captureTiming.block_scope && clientRequestId) {
    const store = new InterviewBlockStore(captureTiming.block_scope);
    const block = (await store.list()).find((item) => item.id === captureTiming.block_id);
    if (!block || block.state !== 'capturing') throw new Error('The active local block is unavailable');
    block.requestId = clientRequestId;
    block.pendingContent = message;
    block.metadata.student_speech = {start_ms: captureTiming.start_ms, end_ms: captureTiming.end_ms};
    await store.patch(block.id, {requestId: clientRequestId, pendingContent: message, metadata: {student_speech: block.metadata.student_speech}});
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
  const response = captureTiming?.block_id
    ? await blockFetch(Number(interviewId), '/messages', init, captureTiming.block_scope)
    : await captureFetch(interviewId, `${API_URL}/medical-interviews/${interviewId}/messages`, init);

  const data: unknown = await response.json();
  if (!response.ok) {
    const detail =
      data &&
      typeof data === 'object' &&
      'detail' in data &&
      typeof data.detail === 'string'
        ? data.detail
        : `Request failed with status ${response.status}`;
    if (captureTiming?.block_id) throw new CaptureSyncError(response.status, detail);
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

  if (captureTiming?.block_id && captureTiming.block_scope) {
    const store = new InterviewBlockStore(captureTiming.block_scope);
    const block = (await store.list()).find((item) => item.id === captureTiming.block_id);
    if (!block) throw new Error('The local block was lost while delivering the response');
    const saved = transformToCamelCase(data.messages) as Message[];
    block.metadata.student_message_id = saved.find((item) => newMessageIds.includes(item.id) && item.senderType === 'user')?.id ?? null;
    block.metadata.patient_message_id = saved.find((item) => newMessageIds.includes(item.id) && item.senderType === 'patient')?.id;
    block.pendingContent = undefined;
    await store.patch(block.id, {pendingContent: undefined, metadata: {
      student_message_id: block.metadata.student_message_id, patient_message_id: block.metadata.patient_message_id,
    }});
  }

  return {
    messages: transformToCamelCase(data.messages) as Message[],
    newMessageIds,
  };
};
