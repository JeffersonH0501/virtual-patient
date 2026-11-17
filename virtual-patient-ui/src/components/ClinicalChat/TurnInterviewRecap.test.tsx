import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {TurnInterviewRecap} from './TurnInterviewRecap';
import type {InterviewRecap} from '../../types/recording';

const actor = vi.hoisted(() => ({role: 'admin'}));
vi.mock('../../hooks/useUser', () => ({useUser: () => ({user: actor})}));
vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: (key: string, values?: {number?: number}) => values?.number == null ? key : `${key} ${values.number}`,
  }),
}));
vi.mock('../../services/recordings', () => ({resolveRecordingSource: (source: string) => source}));

afterEach(() => {
 cleanup(); vi.restoreAllMocks(); actor.role = 'admin';
});

const baseRecap = (): InterviewRecap => ({
  interviewId: 7, recordingStatus: 'complete', durationMs: 4000,
  replay: {status: 'ready', progress: 100, source: '/replay.mp4'},
  turnMedia: [{turnMediaId: 'clip-1', sessionClockMs: 0, durationMs: 4000, studentVideoSource: '/student.webm', messageId: 1, metadata: {messageId: 1, sessionClockMs: 0}}],
  turns: [
    {turnId: 'turn-patient', speaker: 'patient', startMs: 0, endMs: 2000, transcript: 'Patient line', inputSource: 'tts', timingSource: 'tts_playback', timingQuality: 'measured'},
    {turnId: 'turn-student', speaker: 'student', startMs: 2000, endMs: 4000, transcript: 'Student line', inputSource: 'camera_microphone', timingSource: 'turn_media', timingQuality: 'measured'},
  ],
});

it('renders the transcript and plays the single replay video', () => {
  const {container} = render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  expect(screen.getByText('Patient line')).toBeTruthy();
  expect(container.querySelectorAll('video')).toHaveLength(1);
  expect(container.querySelector('video')?.getAttribute('src')).toBe('/replay.mp4');
  expect(container.querySelector('audio')).toBeNull();
});

it('shows the preparation progress instead of a video while the replay is built', () => {
  const recap: InterviewRecap = {...baseRecap(), replay: {status: 'processing', progress: 37}};
  const {container} = render(<TurnInterviewRecap recap={recap} infoDisabled={false} />);
  expect(container.querySelector('video')).toBeNull();
  expect(screen.getByRole('status').textContent).toContain('clinicalChat.recap.preparing');
  expect(container.querySelector('.calibration-processing-mark')).not.toBeNull();
  expect(screen.queryByRole('button', {name: 'clinicalChat.recap.play'})).toBeNull();
  expect(container.querySelector('img')).toBeNull();
  expect(screen.getByText('Student line').closest('button')).toHaveProperty('disabled', true);
});

it('seeks the video when a transcript bubble is clicked', () => {
  const {container} = render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  const video = container.querySelector('video')!;
  fireEvent.click(screen.getByText('Student line'));
  expect(video.currentTime).toBe(2);
});

it('scrolls the requested turn bubble into view on a jump request', () => {
  const scrollIntoView = vi.fn();
  // jsdom does not implement scrollIntoView; provide it to observe the jump.
  HTMLElement.prototype.scrollIntoView = scrollIntoView;
  const {rerender} = render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  expect(scrollIntoView).not.toHaveBeenCalled();
  rerender(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} seekRequest={{turnId: 'turn-student', requestId: 1}} />);
  expect(scrollIntoView).toHaveBeenCalledWith({block: 'nearest'});
});

it('allows admin to open turn details and closes them on infoDisabled', () => {
  const {rerender} = render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  fireEvent.click(screen.getByRole('button', {name: /clinicalChat\.recap\.turnInfo: clinicalChat\.recap\.turnNumber 1/}));
  expect(screen.getByText('clinicalChat.recap.turnDetails')).toBeTruthy();
  rerender(<TurnInterviewRecap recap={baseRecap()} infoDisabled={true} />);
  expect(screen.queryByText('clinicalChat.recap.turnDetails')).toBeNull();
});

it('hides turn-info buttons for non-admin users', () => {
  actor.role = 'student';
  render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  expect(screen.queryByRole('button', {name: /clinicalChat\.recap\.turnInfo/})).toBeNull();
});

it('keeps the previous turn highlighted while the reply is prepared and after the last reply', async () => {
  const {highlightedMessage} = await import('./useTurnPlayback');
  const clip = (startMs: number, durationMs: number, messageId: number | null, speaker: 'student' | 'patient', voiceStartMs: number | null = null) =>
    ({startMs, durationMs, messageId, speaker, voiceStartMs});
  const clips = [clip(0, 2000, 1, 'student'), clip(2000, 5000, 2, 'patient', 3000), clip(7000, 2000, 3, 'patient'), clip(9000, 3000, null, 'student')];
  expect(highlightedMessage(clips, 1000)).toBe(1);
  expect(highlightedMessage(clips, 4000)).toBe(1);
  expect(highlightedMessage(clips, 5100)).toBe(2);
  expect(highlightedMessage(clips, 7500)).toBe(3);
  expect(highlightedMessage(clips, 10000)).toBe(3);
});

it('marks the patient as speaking only inside the recorded voice window', async () => {
  const {patientSpeakingAt} = await import('./useTurnPlayback');
  const clips = [{startMs: 2000, durationMs: 5000, messageId: 2, speaker: 'patient' as const, voiceStartMs: 3000, voiceEndMs: 4500}];
  expect(patientSpeakingAt(clips, 4000)).toBe(false);
  expect(patientSpeakingAt(clips, 5500)).toBe(true);
  expect(patientSpeakingAt(clips, 6600)).toBe(false);
});
