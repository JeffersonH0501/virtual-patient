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

afterEach(() => { cleanup(); vi.restoreAllMocks(); actor.role = 'admin'; });

const baseRecap = (): InterviewRecap => ({
  interviewId: 7, recordingStatus: 'complete', durationMs: 4000,
  turnMedia: [{turnMediaId: 'clip-1', sessionClockMs: 0, durationMs: 4000, studentVideoSource: '/student.webm', messageId: 1, metadata: {messageId: 1, sessionClockMs: 0}}],
  turns: [
    {turnId: 'turn-patient', speaker: 'patient', startMs: 0, endMs: 2000, transcript: 'Patient line', inputSource: 'tts', timingSource: 'tts_playback', timingQuality: 'measured'},
    {turnId: 'turn-student', speaker: 'student', startMs: 2000, endMs: 4000, transcript: 'Student line', inputSource: 'camera_microphone', timingSource: 'turn_media', timingQuality: 'measured'},
  ],
});

it('renders the transcript and a playback timeline', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  expect(screen.getByText('Patient line')).toBeTruthy();
  expect(screen.getByText('Student line')).toBeTruthy();
  expect(screen.getByRole('slider', {name: 'clinicalChat.recap.timeline'})).toBeTruthy();
});

it('renders a video element for the student turn clip', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const {container} = render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  const video = container.querySelector('video');
  expect(video).not.toBeNull();
  expect(video!.getAttribute('src')).toBe('/student.webm');
});

it('shows no video when turnMedia is empty', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const recap: InterviewRecap = {...baseRecap(), turnMedia: []};
  const {container} = render(<TurnInterviewRecap recap={recap} infoDisabled={false} />);
  expect(container.querySelector('video')).toBeNull();
  expect(screen.getByRole('status')).toBeTruthy();
});

it('allows admin to open turn details and closes them on infoDisabled', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const {rerender} = render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  fireEvent.click(screen.getAllByRole('button', {name: 'clinicalChat.recap.turnInfo'})[0]);
  expect(screen.getByText('clinicalChat.recap.turnDetails')).toBeTruthy();
  rerender(<TurnInterviewRecap recap={baseRecap()} infoDisabled={true} />);
  expect(screen.queryByText('clinicalChat.recap.turnDetails')).toBeNull();
});

it('hides turn-info buttons for non-admin users', () => {
  actor.role = 'student';
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  render(<TurnInterviewRecap recap={baseRecap()} infoDisabled={false} />);
  expect(screen.queryByRole('button', {name: 'clinicalChat.recap.turnInfo'})).toBeNull();
});

it('turn seek buttons are disabled when timing is unavailable', () => {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined);
  const recap: InterviewRecap = {
    ...baseRecap(),
    turns: [{turnId: 't1', speaker: 'patient', transcript: 'No timing', inputSource: 'tts', timingSource: 'unavailable', timingQuality: 'estimated'}],
  };
  render(<TurnInterviewRecap recap={recap} infoDisabled={false} />);
  expect(screen.getByText('No timing').closest('button')).toHaveProperty('disabled', true);
});
