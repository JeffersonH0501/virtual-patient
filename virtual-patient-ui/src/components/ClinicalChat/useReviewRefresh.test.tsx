import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {useReviewRefresh} from './useReviewRefresh';
import type {InterviewRecap} from '../../types/recording';

const service = vi.hoisted(() => ({recap: vi.fn(), regenerate: vi.fn(), reprocess: vi.fn()}));
vi.mock('../../services/recordings', () => ({getInterviewRecap: service.recap,
  regenerateInterviewEvaluation: service.regenerate, reprocessInterviewRecording: service.reprocess}));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });

it('does not publish a response from a refresh belonging to a previous interview', async () => {
  vi.useFakeTimers();
  service.regenerate.mockResolvedValue(undefined);
  let resolve!: (value: InterviewRecap) => void;
  service.recap.mockReturnValue(new Promise((done) => { resolve = done; }));
  const options = {interviewId: 7, role: 'superuser' as const, mode: 'review' as const, isCompleted: true,
    recapData: null, setRecapData: vi.fn(), fetchInterview: vi.fn()};
  const {result, rerender} = renderHook((value) => useReviewRefresh(value), {initialProps: options});
  let pending!: Promise<void>;
  await act(async () => { pending = result.current.handleRefresh(false); });
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  rerender({...options, interviewId: 8});
  await act(async () => {
    resolve({interviewId: 7, turns: [], recordingStatus: 'ready', evaluationProcessing: {status: 'complete'}});
    await pending;
  });
  expect(options.setRecapData).not.toHaveBeenCalled();
  expect(options.fetchInterview).not.toHaveBeenCalled();
  expect(result.current.isRegenerating).toBe(false);
});

it('cancels its pending poll timer on unmount', async () => {
  vi.useFakeTimers();
  service.regenerate.mockResolvedValue(undefined);
  const {result, unmount} = renderHook(() => useReviewRefresh({interviewId: 7, role: 'superuser', mode: 'review',
    isCompleted: true, recapData: null, setRecapData: vi.fn(), fetchInterview: vi.fn()}));
  await act(async () => { void result.current.handleRefresh(false); });
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
