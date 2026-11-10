import {afterEach, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {InterviewRecap} from './InterviewRecap';
import {getInterviewRecap} from '../../services/recordings';
const actor = vi.hoisted(() => ({role: 'superuser'}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: actor})}));
vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: (key: string, values?: {number?: number}) => values?.number == null ? key : `${key} ${values.number}`,
  }),
}));
vi.mock('../../services/recordings', () => ({
  resolveRecordingSource: (source: string) => source,
  getInterviewRecap: vi.fn(async () => ({interviewId: 7, recordingStatus: 'complete', durationMs: 60000,
    blocks: [{blockId: 'one', offsetMs: 0, durationMs: 60000, studentVideoSource: '/student.webm', patientAudioSource: null, metadata: {patientMessageId: 1}}],
    turns: [{turnId: 'real-uuid', speaker: 'patient', startMs: 16000, endMs: 18000, transcript: 'A concern', inputSource: 'audio', timingSource: 'recording', timingQuality: 'measured'}]})),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  actor.role = 'superuser';
  vi.useRealTimers();
});
it('allows the superuser to open turn details and closes them when that role is lost', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const {rerender} = render(<InterviewRecap interviewId={7} />);
  await screen.findByText('A concern');
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.recap.turnInfo'}));
  expect(screen.getByText('clinicalChat.recap.turnDetails')).toBeTruthy();
  actor.role = 'student';
  rerender(<InterviewRecap interviewId={7} />);
  expect(screen.queryByText('clinicalChat.recap.turnDetails')).toBeNull();
});
it('keeps the transcript available when recording media and timestamps are missing', async () => {
  vi.mocked(getInterviewRecap).mockResolvedValueOnce({interviewId: 7, recordingStatus: 'unavailable', turns: [
    {turnId: 'first', speaker: 'patient', transcript: 'First untimed turn', inputSource: 'text', timingSource: 'unavailable', timingQuality: 'estimated'},
    {turnId: 'second', speaker: 'student', transcript: 'Second untimed turn', inputSource: 'text', timingSource: 'unavailable', timingQuality: 'estimated'},
  ]});
  const {rerender} = render(<InterviewRecap interviewId={7} />);
  await screen.findByText('First untimed turn');
  expect(screen.getByText('First untimed turn').closest('button')).toHaveProperty('disabled', true);
  rerender(<InterviewRecap interviewId={7} seekRequest={{turnId: 'second', requestId: 1}} />);
  expect(screen.getByText('Second untimed turn').closest('button')).toHaveProperty('disabled', true);
});

it('keeps the loaded recording on a rerender of the same interview', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const {container, rerender} = render(<InterviewRecap interviewId={7} />);
  await screen.findByText('A concern');
  const video = container.querySelector('video');
  rerender(<InterviewRecap interviewId={7} />);
  expect(video).not.toBeNull();
  expect(container.querySelector('video')).toBe(video);
});

it('closes technical details when evidence becomes unavailable during processing', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const {rerender} = render(<InterviewRecap interviewId={7} />);
  await screen.findByText('A concern');
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.recap.turnInfo'}));
  expect(screen.getByText('clinicalChat.recap.turnDetails')).toBeTruthy();
  rerender(<InterviewRecap interviewId={7} infoDisabled />);
  expect(screen.queryByText('clinicalChat.recap.turnDetails')).toBeNull();
});

it('preserves turn timing, numeric formatting and unavailable evidence in details', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  vi.mocked(getInterviewRecap).mockResolvedValueOnce({interviewId: 7, recordingStatus: 'complete', turns: [{
    turnId: 'details', speaker: 'student', startMs: 1000, endMs: 3000, transcript: 'Synthetic details',
    inputSource: 'text', timingSource: 'recording', timingQuality: 'measured',
    paraverbal: {processed: {speechRateWpm: 123.45678}, status: 'ok'},
  }]});
  render(<InterviewRecap interviewId={7} />);
  await screen.findByText('Synthetic details');
  fireEvent.click(screen.getByRole('button', {name: 'clinicalChat.recap.turnInfo'}));
  expect(screen.getByText('0:02 (2000 ms)')).toBeDefined();
  expect(screen.getByText('123.457')).toBeDefined();
  expect(screen.getByText('clinicalChat.recap.nonverbalUnavailable')).toBeDefined();
});

it('does not show the previous recap while the next interview is loading', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  vi.mocked(getInterviewRecap).mockResolvedValueOnce({interviewId: 7, recordingStatus: 'ready', durationMs: 1000,
    blocks: [{blockId: 'old', offsetMs: 0, durationMs: 1000, studentVideoSource: '/old.webm', metadata: {}}],
    turns: [{turnId: 'old', speaker: 'student', transcript: 'A concern', inputSource: 'microphone', timingSource: 'block_speech', timingQuality: 'measured'}]});
  const {rerender} = render(<InterviewRecap interviewId={7} />);
  await screen.findByText('A concern');
  let resolve!: (value: Awaited<ReturnType<typeof getInterviewRecap>>) => void;
  vi.mocked(getInterviewRecap).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  rerender(<InterviewRecap interviewId={8} />);
  expect(screen.queryByText('A concern')).toBeNull();
  await act(async () => resolve({interviewId: 8, recordingStatus: 'unavailable', turns: []}));
});

it('keeps confirmed recap media on a polling error and offers a retry', async () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const saved = {interviewId: 7, recordingStatus: 'ready' as const, durationMs: 1000, blocks: [{blockId: 'kept', offsetMs: 0, durationMs: 1000, studentVideoSource: '/kept.webm', patientAudioSource: null, metadata: {patientMessageId: 1}}],
    turns: [], observationProcessing: {status: 'queued'}};
  vi.mocked(getInterviewRecap).mockResolvedValueOnce(saved).mockRejectedValueOnce(new Error('Synthetic network failure'));
  vi.useFakeTimers();
  let container!: HTMLElement;
  await act(async () => { container = render(<InterviewRecap interviewId={7} />).container; });
  const video = container.querySelector('video');
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(container.querySelector('video')).toBe(video);
  expect(screen.getByRole('alert').textContent).toContain('clinicalChat.recap.loadFailed');
  vi.mocked(getInterviewRecap).mockResolvedValueOnce({...saved, observationProcessing: {status: 'complete'}});
  await act(async () => { fireEvent.click(screen.getByRole('button', {name: 'common.retry'})); });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(container.querySelector('video')).toBe(video);
});
